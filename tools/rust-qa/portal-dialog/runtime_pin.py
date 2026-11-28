"""Identify the single public freedesktop runtime deployment that a private portal trial may mount."""

import configparser
import hashlib
import json
import os
from pathlib import Path
import platform
import re


PLATFORM = 'org.freedesktop.Platform'
BRANCH = '26.08'
COMMITS = {
    'x86_64': 'df26daaf9d07610b4a72cc4585566194051275ac68396597b06474396f66427c',
    'aarch64': 'b66eec6a19d747f56191c318c11a6ec765b8d7cc45cf16e4926349a64504d620',
}


def runner_temp():
    expected = {'GITHUB_ACTIONS': 'true', 'RUNNER_OS': 'Linux', 'RUNNER_ENVIRONMENT': 'github-hosted',
                'GITHUB_REF': 'refs/heads/rewrite/rust', 'GITHUB_REPOSITORY': 'VoltKraft/immich-folder-watch'}
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise RuntimeError('Hosted runtime acquisition and overrides require a disposable Linux rewrite job')
    temp = Path(os.environ['RUNNER_TEMP'])
    if not temp.is_absolute() or not temp.is_dir():
        raise RuntimeError('A Linux runner temporary directory is required')
    return temp.resolve(strict=True)


def deployment(hosted_path):
    arch = platform.machine()
    if arch not in COMMITS:
        raise RuntimeError(f'No reviewed public Platform commit for {arch}')
    commit = COMMITS[arch]
    suffix = Path('runtime', PLATFORM, arch, BRANCH, commit)
    if hosted_path is None:
        source = Path('/var/lib/flatpak') / suffix
        receipt = None
    else:
        temp = runner_temp()
        relative = hosted_path.relative_to(temp)
        if (len(relative.parts) != len(suffix.parts) + 2
                or not re.fullmatch(r'ifw-portal-platform-[a-zA-Z0-9_-]+', relative.parts[0])
                or relative.parts[1] != 'flatpak' or Path(*relative.parts[2:]) != suffix):
            raise RuntimeError('Only the reviewed native Platform under the fresh runner installation is accepted')
        source = temp / relative
        prepared = temp / relative.parts[0]
        receipt = json.loads((prepared / 'verified.json').read_text())
        signature_digest = hashlib.sha256((prepared / 'signature.txt').read_bytes()).hexdigest()
        if (receipt['ref'] != 'runtime/' + '/'.join((PLATFORM, arch, BRANCH)) or receipt['commit'] != commit
                or receipt['gpg_verify'] is not True or receipt['gpg_verify_summary'] is not True
                or receipt['signature_sha256'] != signature_digest):
            raise RuntimeError('The acquisition record differs from the reviewed signed runtime')
    files = source / 'files'
    if source.resolve(strict=True) != source or files.is_symlink() or not files.is_dir():
        raise RuntimeError('The immutable runtime deployment directory is missing or redirected')
    metadata = source / 'metadata'
    if metadata.is_symlink() or not metadata.is_file():
        raise RuntimeError('The runtime requires its own regular deployment metadata')
    contents = configparser.ConfigParser(interpolation=None, strict=False)
    contents.read(metadata, encoding='utf-8')
    if (contents['Runtime'].get('name') != PLATFORM
            or contents['Runtime'].get('runtime') != '/'.join((PLATFORM, arch, BRANCH))):
        raise RuntimeError('Flatpak runtime metadata does not identify the expected native platform')
    digest = hashlib.sha256(metadata.read_bytes()).hexdigest()
    if receipt is not None and receipt['metadata_sha256'] != digest:
        raise RuntimeError('Installed runtime metadata changed after the signed acquisition')
    return source, {'ref': 'runtime/' + '/'.join((PLATFORM, arch, BRANCH)), 'commit': commit,
                    'metadata_sha256': digest, 'acquisition': receipt or 'local system deployment'}
