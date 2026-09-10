// Create maintenance updates only after Flathub has accepted the initial app.
const fs = require('node:fs/promises');
const path = require('node:path');

const APP_ID = 'io.github.voltkraft.immich-folder-watch';
const TARGET = { owner: 'flathub', repo: APP_ID };
const FILES = [`${APP_ID}.yml`, 'nuget-sources.json'];
const TAG_PATTERN = /^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

function version(tag) {
    const match = TAG_PATTERN.exec(tag);
    if (!match || match[0] !== tag) throw new Error(`Expected a stable vMAJOR.MINOR.PATCH tag, received ${tag}.`);
    return match.slice(1).map(BigInt);
}

function compareVersions(left, right) {
    for (let index = 0; index < left.length; index++) {
        if (left[index] !== right[index]) return left[index] > right[index] ? 1 : -1;
    }
    return 0;
}

function manifestIdentity(text, upstream) {
    // The checked-in template deliberately has one Git source. Fail closed if
    // its structure changes instead of trying to implement a YAML parser here.
    function field(name) {
        const matches = [...text.matchAll(new RegExp(`^\\s*${name}:\\s*(\\S+)\\s*$`, 'gm'))];
        if (matches.length !== 1) throw new Error(`Manifest must have exactly one ${name} field.`);
        return matches[0][1];
    }
    if (field('app-id') !== APP_ID || [...text.matchAll(/^\s*- type: git\s*$/gm)].length !== 1) {
        throw new Error('Manifest must describe the expected app and exactly one Git source.');
    }
    const expectedUrl = `https://github.com/${upstream.owner}/${upstream.repo}.git`;
    if (field('url').toLowerCase() !== expectedUrl.toLowerCase()) {
        throw new Error('Manifest Git source does not match the upstream repository.');
    }
    const tag = field('tag');
    const commit = field('commit');
    if (!/^[0-9a-f]{40}$/.test(commit)) throw new Error('Manifest commit must be a full lowercase Git SHA.');
    return { tag, commit, version: version(tag) };
}

/**
 * Submit the prepared manifest and offline feed as one Flathub maintenance PR.
 * github/context/core are injected by actions/github-script. No target files
 * other than FILES can be written; existing branches are never overwritten.
 * autoMerge must only be enabled after Flathub grants the app that capability.
 */
module.exports = async function updateFlathub({ github, context, core, directory, tag, autoMerge = false }) {
    const requestedVersion = version(tag);
    if (typeof autoMerge !== 'boolean') throw new Error('autoMerge must be a boolean.');
    const upstream = context.repo;
    const contents = Object.fromEntries(await Promise.all(FILES.map(async name => [
        name, await fs.readFile(path.join(directory, name), 'utf8'),
    ])));
    const prepared = manifestIdentity(contents[FILES[0]], upstream);
    if (prepared.tag !== tag) throw new Error('Prepared manifest tag does not match the selected release.');
    const sources = JSON.parse(contents[FILES[1]]);
    if (!Array.isArray(sources) || sources.length === 0) throw new Error('The offline NuGet feed must be a nonempty JSON array.');

    function report(status, url) {
        core.info(url ? `${status}: ${url}` : status);
        core.setOutput('status', status);
        if (url) core.setOutput('pull_request_url', url);
        return { status, ...(url ? { url } : {}) };
    }

    async function isLatestRelease() {
        const { data } = await github.rest.repos.getLatestRelease(upstream);
        if (data.draft || data.prerelease || !data.published_at) throw new Error('Latest upstream release is not a published stable release.');
        return data.tag_name === tag;
    }

    if (!await isLatestRelease()) return report('skipped-stale-release');
    const { data: releaseCommit } = await github.rest.repos.getCommit({ ...upstream, ref: tag });
    if (releaseCommit.sha !== prepared.commit) throw new Error('Prepared manifest commit does not match the upstream release tag.');

    async function getRef(ref, optional = false) {
        try {
            return (await github.rest.git.getRef({ ...TARGET, ref: `heads/${ref}` })).data.object.sha;
        } catch (error) {
            if (error.status === 404 && optional) return null;
            if (error.status === 404) throw new Error('The accepted Flathub app repository and master branch must already exist; initial submission is manual.');
            throw error;
        }
    }

    async function remoteFile(name, ref) {
        let data;
        try {
            ({ data } = await github.rest.repos.getContent({ ...TARGET, path: name, ref }));
        } catch (error) {
            if (error.status === 404) throw new Error(`Required Flathub file ${name} is missing; initial submission and configuration are manual.`);
            throw error;
        }
        if (data.type !== 'file' || data.encoding !== 'base64' || typeof data.content !== 'string') {
            throw new Error(`Cannot read ordinary Flathub file ${name}.`);
        }
        return Buffer.from(data.content, 'base64').toString('utf8');
    }

    const masterSha = await getRef('master');
    const config = JSON.parse(await remoteFile('flathub.json', masterSha));
    if (config['disable-external-data-checker'] !== true) {
        throw new Error('Flathub must set disable-external-data-checker=true before enabling this updater.');
    }
    const arches = config['only-arches'];
    const skippedArches = config['skip-arches'];
    if (!Array.isArray(arches) || arches.length !== 2 ||
        !arches.includes('x86_64') || !arches.includes('aarch64') ||
        (skippedArches !== undefined && (!Array.isArray(skippedArches) || skippedArches.length !== 0))) {
        throw new Error('Flathub must enable exactly x86_64 and aarch64 with no skipped architectures before enabling this updater.');
    }
    const current = manifestIdentity(await remoteFile(FILES[0], masterSha), upstream);
    await remoteFile(FILES[1], masterSha);
    const comparison = compareVersions(requestedVersion, current.version);
    if (comparison < 0) throw new Error(`Refusing to downgrade Flathub from ${current.tag} to ${tag}.`);
    if (comparison === 0) {
        if (current.commit !== prepared.commit) throw new Error('Flathub already has this version with a different commit.');
        return report('already-current');
    }

    const branch = `update-${tag}`;
    async function existingPullRequest() {
        const pulls = await github.paginate(github.rest.pulls.list, {
            ...TARGET, state: 'all', head: `${TARGET.owner}:${branch}`, base: 'master', per_page: 100,
        });
        if (pulls.some(pull => pull.state !== 'open')) {
            throw new Error('This update branch has a closed PR; resolve it manually instead of reopening a rejected update.');
        }
        if (pulls.length > 1) throw new Error('Multiple open PRs use the update branch.');
        return pulls[0] ?? null;
    }

    async function validateBranch(sha) {
        for (const name of FILES) {
            if (await remoteFile(name, sha) !== contents[name]) {
                throw new Error(`Existing update branch differs in ${name}; refusing to overwrite manual changes.`);
            }
        }
        const { data } = await github.rest.repos.compareCommits({ ...TARGET, base: masterSha, head: sha });
        if (!Array.isArray(data.files) || data.files.some(file => !FILES.includes(file.filename) || file.previous_filename)) {
            throw new Error('Existing update branch changes files outside the two prepared package files.');
        }
    }

    let pull = await existingPullRequest();
    let branchSha = await getRef(branch, true);
    if (pull && !branchSha) throw new Error('The existing update PR has no branch; resolve it manually.');
    if (branchSha) {
        await validateBranch(branchSha);
    } else {
        if (!await isLatestRelease()) return report('skipped-stale-release');
        const { data: baseCommit } = await github.rest.git.getCommit({ ...TARGET, commit_sha: masterSha });
        const entries = [];
        for (const name of FILES) {
            const { data: blob } = await github.rest.git.createBlob({
                ...TARGET, encoding: 'base64', content: Buffer.from(contents[name]).toString('base64'),
            });
            entries.push({ path: name, mode: '100644', type: 'blob', sha: blob.sha });
        }
        const { data: tree } = await github.rest.git.createTree({ ...TARGET, base_tree: baseCommit.tree.sha, tree: entries });
        const { data: commit } = await github.rest.git.createCommit({
            ...TARGET, message: `Update to ${tag}`, tree: tree.sha, parents: [masterSha],
        });
        if (await getRef('master') !== masterSha) throw new Error('Flathub master changed during preparation; rerun the update.');
        try {
            await github.rest.git.createRef({ ...TARGET, ref: `refs/heads/${branch}`, sha: commit.sha });
        } catch (error) {
            // Another run may have created the deterministic branch. Validate
            // its complete package diff before accepting that concurrent run.
            if (error.status !== 422) throw error;
        }
        branchSha = await getRef(branch);
        await validateBranch(branchSha);
    }

    if (!await isLatestRelease()) return report('skipped-stale-release');
    pull = await existingPullRequest();
    if (!pull) {
        try {
            ({ data: pull } = await github.rest.pulls.create({
                ...TARGET,
                head: branch,
                base: 'master',
                title: `Update to ${tag}`,
                body: `Update to [${tag}](https://github.com/${upstream.owner}/${upstream.repo}/releases/tag/${tag}).\n\nPin the release commit and regenerate the offline NuGet sources for x86_64 and aarch64.`,
            }));
        } catch (error) {
            if (error.status !== 422) throw error;
            pull = await existingPullRequest();
            if (!pull) throw error;
        }
    }
    if (pull.head.sha !== branchSha) throw new Error('Update PR head changed; refusing to enable automatic merging.');
    if (autoMerge && !pull.auto_merge) {
        await github.graphql(`mutation($pullRequestId: ID!) {
            enablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId, mergeMethod: MERGE}) {
                pullRequest { url }
            }
        }`, { pullRequestId: pull.node_id });
    }
    return report('pull-request-ready', pull.html_url);
};
