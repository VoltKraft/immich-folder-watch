const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const updateFlathub = require('../update-flathub-pr.cjs');

const APP_ID = 'io.github.voltkraft.immich-folder-watch';
const MANIFEST = `${APP_ID}.yml`;
const UPSTREAM = { owner: 'VoltKraft', repo: 'immich-folder-watch' };
const OLD_COMMIT = 'a'.repeat(40);
const NEW_COMMIT = 'b'.repeat(40);
const MASTER = 'c'.repeat(40);
const BRANCH = 'update-v1.1.0';
const FEED = JSON.stringify([{ type: 'file', url: 'https://api.nuget.org/v3-flatcontainer/example/1.0.0/example.1.0.0.nupkg', sha256: 'd'.repeat(64), dest: 'nuget-sources' }]);

function manifest(tag = 'v1.1.0', commit = NEW_COMMIT) {
    return `app-id: ${APP_ID}\nmodules:\n  - name: immich-folder-watch\n    sources:\n      - type: git\n        url: https://github.com/VoltKraft/immich-folder-watch.git\n        tag: ${tag}\n        commit: ${commit}\n      - nuget-sources.json\n`;
}

function sdkArchive(arch, runtime) {
    return `      - type: archive\n        dest: dotnet-sdk\n        only-arches: [${arch}]\n` +
        `        url: https://builds.dotnet.microsoft.com/dotnet/Sdk/10.0.401/dotnet-sdk-10.0.401-${runtime}.tar.gz\n` +
        `        sha512: ${'d'.repeat(128)}\n`;
}

function manifestWithSdkArchives(tag = 'v1.1.0', commit = NEW_COMMIT) {
    return manifest(tag, commit)
        .replace('      - type: git\n', sdkArchive('x86_64', 'linux-x64') + '      - type: git\n')
        .replace('      - nuget-sources.json\n', sdkArchive('aarch64', 'linux-arm64') + '      - nuget-sources.json\n');
}

function apiError(status) {
    return Object.assign(new Error(`HTTP ${status}`), { status });
}

async function fixture(t, options = {}) {
    const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'flathub-update-test-'));
    t.after(() => fs.rm(directory, { recursive: true, force: true }));
    const prepared = { [MANIFEST]: manifest(), 'nuget-sources.json': FEED };
    for (const [name, content] of Object.entries(prepared)) await fs.writeFile(path.join(directory, name), content);
    const state = {
        calls: [],
        outputs: {},
        latest: 'v1.1.0',
        releaseCommit: NEW_COMMIT,
        refs: { master: MASTER },
        blobs: {},
        trees: {},
        commits: {
            [MASTER]: {
                [MANIFEST]: manifest('v1.0.0', OLD_COMMIT),
                'nuget-sources.json': '[{"old":true}]',
                'flathub.json': '{"only-arches":["x86_64","aarch64"],"disable-external-data-checker":true}',
                '.github/workflows/check.yml': 'existing workflow',
            },
        },
        pulls: [],
        ...options,
    };
    const hash = value => crypto.createHash('sha1').update(value).digest('hex');
    const call = (name, action) => async args => {
        state.calls.push({ name, args });
        if (!name.startsWith('upstream.') && name !== 'graphql') {
            assert.equal(args.owner, 'flathub');
            assert.equal(args.repo, APP_ID);
        }
        return { data: await action(args) };
    };
    const github = {
        rest: {
            repos: {
                getLatestRelease: call('upstream.getLatestRelease', () => ({ tag_name: state.latest, published_at: '2026-09-10T00:00:00Z', draft: false, prerelease: false })),
                getCommit: call('upstream.getCommit', () => ({ sha: state.releaseCommit })),
                getContent: call('repos.getContent', args => {
                    const content = state.commits[args.ref]?.[args.path];
                    if (content === undefined) throw apiError(404);
                    return { type: 'file', encoding: 'base64', content: Buffer.from(content).toString('base64') };
                }),
                compareCommits: call('repos.compareCommits', args => ({
                    files: [...new Set([...Object.keys(state.commits[args.base]), ...Object.keys(state.commits[args.head])])]
                        .filter(name => state.commits[args.base][name] !== state.commits[args.head][name])
                        .map(filename => ({ filename, status: 'modified' })),
                })),
            },
            git: {
                getRef: call('git.getRef', args => {
                    const sha = state.refs[args.ref.replace(/^heads\//, '')];
                    if (!sha) throw apiError(404);
                    return { object: { type: 'commit', sha } };
                }),
                getCommit: call('git.getCommit', args => ({ sha: args.commit_sha, tree: { sha: args.commit_sha } })),
                createBlob: call('git.createBlob', args => {
                    assert.equal(args.encoding, 'base64');
                    const content = Buffer.from(args.content, 'base64').toString('utf8');
                    const sha = hash(content);
                    state.blobs[sha] = content;
                    return { sha };
                }),
                createTree: call('git.createTree', args => {
                    assert.deepEqual(args.tree.map(entry => entry.path), [MANIFEST, 'nuget-sources.json']);
                    const tree = { ...state.commits[args.base_tree] };
                    for (const entry of args.tree) {
                        assert.equal(entry.mode, '100644');
                        assert.equal(entry.type, 'blob');
                        tree[entry.path] = state.blobs[entry.sha];
                    }
                    const sha = hash(JSON.stringify(tree));
                    state.trees[sha] = tree;
                    return { sha };
                }),
                createCommit: call('git.createCommit', args => {
                    assert.deepEqual(args.parents, [MASTER]);
                    const sha = hash(JSON.stringify(args));
                    state.commits[sha] = state.trees[args.tree];
                    return { sha };
                }),
                createRef: call('git.createRef', args => {
                    const branch = args.ref.replace(/^refs\/heads\//, '');
                    if (state.refs[branch]) throw apiError(422);
                    state.refs[branch] = args.sha;
                    return { ref: args.ref, object: { sha: args.sha } };
                }),
            },
            pulls: {
                list: call('pulls.list', () => state.pulls),
                create: call('pulls.create', args => {
                    assert.equal(args.head, BRANCH);
                    assert.equal(args.base, 'master');
                    const pull = {
                        number: 1, node_id: 'PR_1', state: 'open', html_url: `https://github.com/flathub/${APP_ID}/pull/1`,
                        head: { sha: state.refs[args.head] }, auto_merge: null,
                    };
                    state.pulls.push(pull);
                    return pull;
                }),
            },
        },
        paginate: async (method, args) => (await method(args)).data,
        graphql: async (query, variables) => {
            state.calls.push({ name: 'graphql', args: { query, variables } });
            state.pulls[0].auto_merge = { merge_method: 'merge' };
            return { enablePullRequestAutoMerge: { pullRequest: { url: state.pulls[0].html_url } } };
        },
    };
    const core = { info: () => {}, setOutput: (name, value) => { state.outputs[name] = value; } };
    const run = overrides => updateFlathub({ github, context: { repo: UPSTREAM }, core, directory, tag: 'v1.1.0', ...overrides });
    const mutations = () => state.calls.filter(call => call.name.includes('.create') || call.name === 'graphql');
    return { state, github, directory, prepared, run, mutations };
}

test('creates one atomic two-file update and reuses the exact branch and PR on retry', async t => {
    const { state, run, mutations, prepared } = await fixture(t);
    const first = await run();
    assert.equal(first.status, 'pull-request-ready');
    assert.equal(state.outputs.pull_request_url, first.url);
    const branchFiles = state.commits[state.refs[BRANCH]];
    for (const [name, content] of Object.entries(prepared)) assert.equal(branchFiles[name], content);
    assert.equal(branchFiles['flathub.json'], state.commits[MASTER]['flathub.json']);
    assert.equal(branchFiles['.github/workflows/check.yml'], 'existing workflow');
    assert.equal(mutations().length, 6);
    assert.deepEqual(await run(), first);
    assert.equal(mutations().length, 6);
});

test('skips a stale published release without any writes', async t => {
    const { run, mutations } = await fixture(t, { latest: 'v1.2.0' });
    assert.deepEqual(await run(), { status: 'skipped-stale-release' });
    assert.equal(mutations().length, 0);
});

test('rejects invalid stable tags, mismatched manifests, and mutable release pins', async t => {
    const { run, mutations, state, directory } = await fixture(t);
    for (const tag of ['v01.1.0', 'v1.1.0-rc.1', '1.1.0', 'v1.1.0+meta', 'v1.1.0\n']) {
        await assert.rejects(run({ tag }), /stable|selected release/);
    }
    await assert.rejects(run({ tag: 'v1.2.0' }), /selected release/);
    state.releaseCommit = OLD_COMMIT;
    await assert.rejects(run(), /does not match the upstream release tag/);
    await fs.writeFile(path.join(directory, MANIFEST), manifest().replace(NEW_COMMIT, 'b'.repeat(7)));
    await assert.rejects(run(), /full lowercase Git SHA/);
    assert.equal(mutations().length, 0);
});

test('requires a nonempty generated offline feed', async t => {
    const { run, mutations, directory } = await fixture(t);
    await fs.writeFile(path.join(directory, 'nuget-sources.json'), '[]');
    await assert.rejects(run(), /nonempty JSON array/);
    assert.equal(mutations().length, 0);
});

test('updates app identity independently of both architecture-specific SDK archive sources', async t => {
    const { run, state, directory } = await fixture(t);
    const content = manifestWithSdkArchives();
    await fs.writeFile(path.join(directory, MANIFEST), content);
    state.commits[MASTER][MANIFEST] = manifestWithSdkArchives('v1.0.0', OLD_COMMIT);

    assert.equal((await run()).status, 'pull-request-ready');

    assert.equal(state.commits[state.refs[BRANCH]][MANIFEST], content);
    assert.equal(state.pulls.length, 1);
});

test('ignores archive and nested checker identity fields outside the direct Git source properties', async t => {
    const { run, state, directory } = await fixture(t);
    const content = manifestWithSdkArchives()
        .replace('        dest: dotnet-sdk\n', `        dest: dotnet-sdk\n        tag: v9.0.0\n        commit: ${OLD_COMMIT}\n`)
        .replace(`        commit: ${NEW_COMMIT}\n`, `        commit: ${NEW_COMMIT}\n` +
            '        x-checker-data:\n          type: json\n          url: https://example.invalid/releases\n' +
            `          tag: v8.0.0\n          commit: ${OLD_COMMIT}\n`);
    await fs.writeFile(path.join(directory, MANIFEST), content);

    assert.equal((await run()).status, 'pull-request-ready');
    assert.equal(state.commits[state.refs[BRANCH]][MANIFEST], content);
});

test('cannot borrow missing Git identity from adjacent archives or nested metadata', async t => {
    const values = { url: 'https://github.com/VoltKraft/immich-folder-watch.git', tag: 'v1.1.0', commit: NEW_COMMIT };
    for (const [field, value] of Object.entries(values)) {
        for (const location of ['archive', 'nested', 'following-section']) {
            const { run, directory, mutations } = await fixture(t);
            let content = manifestWithSdkArchives().replace(`        ${field}: ${value}\n`, '');
            if (location === 'archive') {
                content = content.replace('        dest: dotnet-sdk\n', `        dest: dotnet-sdk\n        ${field}: ${value}\n`);
            } else if (location === 'nested') {
                content = content.replace('      - type: git\n', `      - type: git\n        metadata:\n          ${field}: ${value}\n`);
            } else {
                content += `    build-commands:\n      - metadata:\n        ${field}: ${value}\n`;
            }
            await fs.writeFile(path.join(directory, MANIFEST), content);
            await assert.rejects(run(), new RegExp(`exactly one ${field} field`));
            assert.equal(mutations().length, 0);
        }
    }
});

test('rejects duplicate Git sources and duplicate direct identity fields with SDK archives present', async t => {
    const variants = [
        manifestWithSdkArchives().replace('      - nuget-sources.json\n',
            '      - type: git # Another app source\n        url: https://example.invalid/other.git\n'),
        manifestWithSdkArchives().replace(`        tag: v1.1.0\n`, '        tag: v1.1.0\n        tag: v1.1.0\n'),
        manifestWithSdkArchives().replace(`        commit: ${NEW_COMMIT}\n`, `        commit: ${NEW_COMMIT}\n        commit:\n`),
        manifestWithSdkArchives().replace('        url: https://github.com/VoltKraft/immich-folder-watch.git\n',
            '        url: https://example.invalid/other.git\n'),
    ];
    for (const content of variants) {
        const { run, directory, mutations } = await fixture(t);
        await fs.writeFile(path.join(directory, MANIFEST), content);
        await assert.rejects(run(), /exactly one Git source|exactly one tag field|exactly one commit field|does not match the upstream repository/);
        assert.equal(mutations().length, 0);
    }
});

test('refuses a downgrade and a reused version with a different commit', async t => {
    const { run, state, mutations } = await fixture(t);
    state.commits[MASTER][MANIFEST] = manifest('v1.2.0');
    await assert.rejects(run(), /downgrade/);
    state.commits[MASTER][MANIFEST] = manifest('v1.1.0', OLD_COMMIT);
    await assert.rejects(run(), /different commit/);
    assert.equal(mutations().length, 0);
});

test('same published version and commit is a no-op', async t => {
    const { run, state, mutations } = await fixture(t);
    state.commits[MASTER][MANIFEST] = manifest();
    assert.deepEqual(await run(), { status: 'already-current' });
    assert.equal(mutations().length, 0);
});

test('requires the accepted app repository, both package files, and disabled external checker', async t => {
    for (const missing of ['repo', MANIFEST, 'nuget-sources.json', 'flathub.json', 'checker']) {
        const { run, state, mutations } = await fixture(t);
        if (missing === 'repo') delete state.refs.master;
        else if (missing === 'checker') state.commits[MASTER]['flathub.json'] = '{"disable-external-data-checker":false}';
        else delete state.commits[MASTER][missing];
        await assert.rejects(run(), /initial submission|disable-external-data-checker/);
        assert.equal(mutations().length, 0);
    }
});

test('refuses updates when the accepted app disables either required architecture', async t => {
    const configurations = [
        {},
        { 'only-arches': ['x86_64'] },
        { 'only-arches': ['aarch64'] },
        { 'only-arches': [] },
        { 'only-arches': ['x86_64', 'x86_64'] },
        { 'only-arches': ['x86_64', 'aarch64', 'i386'] },
        ...[['aarch64'], ['x86_64'], ['i386'], null, 'aarch64'].map(skipped => ({
            'only-arches': ['x86_64', 'aarch64'], 'skip-arches': skipped,
        })),
    ];
    for (const configuration of configurations) {
        const { run, state, mutations } = await fixture(t);
        state.commits[MASTER]['flathub.json'] = JSON.stringify({
            'disable-external-data-checker': true, ...configuration,
        });
        await assert.rejects(run({ autoMerge: true }), /exactly x86_64 and aarch64 with no skipped architectures/);
        assert.equal(mutations().length, 0);
    }
});

test('accepts either architecture order and an explicitly empty skip list', async t => {
    for (const arches of [['x86_64', 'aarch64'], ['aarch64', 'x86_64']]) {
        const { run, state } = await fixture(t);
        state.commits[MASTER]['flathub.json'] = JSON.stringify({
            'disable-external-data-checker': true, 'only-arches': arches, 'skip-arches': [],
        });
        assert.equal((await run()).status, 'pull-request-ready');
    }
});

test('resumes an exact branch left behind before PR creation', async t => {
    const { run, state, prepared, mutations } = await fixture(t);
    state.refs[BRANCH] = 'e'.repeat(40);
    state.commits[state.refs[BRANCH]] = { ...state.commits[MASTER], ...prepared };
    assert.equal((await run()).status, 'pull-request-ready');
    assert.deepEqual(mutations().map(call => call.name), ['pulls.create']);
});

test('refuses manual edits to either package file or another branch file', async t => {
    for (const name of [MANIFEST, 'nuget-sources.json', '.github/workflows/check.yml']) {
        const { run, state, prepared, mutations } = await fixture(t);
        state.refs[BRANCH] = 'e'.repeat(40);
        state.commits[state.refs[BRANCH]] = { ...state.commits[MASTER], ...prepared, [name]: 'manual edit' };
        await assert.rejects(run(), /manual changes|outside the two/);
        assert.equal(mutations().length, 0);
    }
});

test('never reopens a closed or rejected PR', async t => {
    const { run, state, mutations } = await fixture(t);
    state.pulls.push({ state: 'closed', number: 1, merged_at: null });
    await assert.rejects(run(), /closed PR/);
    assert.equal(mutations().length, 0);
});

test('requests GitHub checked auto-merge only when explicitly enabled', async t => {
    const { run, state } = await fixture(t);
    await run();
    assert.equal(state.calls.filter(call => call.name === 'graphql').length, 0);
    await run({ autoMerge: true });
    const requests = state.calls.filter(call => call.name === 'graphql');
    assert.equal(requests.length, 1);
    assert.match(requests[0].args.query, /enablePullRequestAutoMerge/);
    assert.match(requests[0].args.query, /mergeMethod: MERGE/);
    assert.deepEqual(requests[0].args.variables, { pullRequestId: 'PR_1' });
    await run({ autoMerge: true });
    assert.equal(state.calls.filter(call => call.name === 'graphql').length, 1);
    await assert.rejects(run({ autoMerge: 'true' }), /boolean/);
});

test('tolerates concurrent creation only when the branch contents and PR are exact', async t => {
    const { run, github, state } = await fixture(t);
    const createRef = github.rest.git.createRef;
    github.rest.git.createRef = async args => {
        await createRef(args);
        throw apiError(422);
    };
    const createPull = github.rest.pulls.create;
    github.rest.pulls.create = async args => {
        await createPull(args);
        throw apiError(422);
    };
    assert.equal((await run()).status, 'pull-request-ready');
    assert.equal(state.pulls.length, 1);
});

test('rejects a concurrent branch with different prepared contents', async t => {
    const { run, github, state } = await fixture(t);
    github.rest.git.createRef = async () => {
        state.refs[BRANCH] = MASTER;
        throw apiError(422);
    };
    await assert.rejects(run(), /manual changes/);
    assert.equal(state.pulls.length, 0);
});

test('rechecks latest release before writing the update', async t => {
    const { run, github, state, mutations } = await fixture(t);
    const listPulls = github.rest.pulls.list;
    github.rest.pulls.list = async args => {
        state.latest = 'v1.2.0';
        return listPulls(args);
    };
    assert.deepEqual(await run(), { status: 'skipped-stale-release' });
    assert.equal(mutations().length, 0);
});

test('does not publish the branch when Flathub master changes during preparation', async t => {
    const { run, github, state } = await fixture(t);
    const createCommit = github.rest.git.createCommit;
    github.rest.git.createCommit = async args => {
        const result = await createCommit(args);
        state.refs.master = 'f'.repeat(40);
        return result;
    };
    await assert.rejects(run(), /master changed/);
    assert.equal(state.refs[BRANCH], undefined);
    assert.equal(state.pulls.length, 0);
});

test('does not auto-merge a PR whose head changed after validation', async t => {
    const { run, state } = await fixture(t);
    await run();
    state.pulls[0].head.sha = 'f'.repeat(40);
    await assert.rejects(run({ autoMerge: true }), /head changed/);
    assert.equal(state.calls.filter(call => call.name === 'graphql').length, 0);
});
