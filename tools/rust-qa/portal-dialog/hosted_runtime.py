"""Acquire the pinned public Platform in a fresh GitHub Actions runner-only user installation."""

import configparser
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile

from runtime_pin import BRANCH, COMMITS, PLATFORM, deployment, runner_temp


def acquire():
    temp = runner_temp()
    arch = platform.machine()
    if arch not in COMMITS:
        raise RuntimeError(f'Unsupported native architecture {arch}')
    expected = COMMITS[arch]
    ref = '/'.join(('runtime', PLATFORM, arch, BRANCH))
    work = Path(tempfile.mkdtemp(prefix='ifw-portal-platform-', dir=temp))
    print('Private runtime acquisition directory', work, flush=True)
    installation = work / 'flatpak'
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(work / 'home'),
           'FLATPAK_USER_DIR': str(installation), 'FLATPAK_SYSTEM_DIR': str(work / 'empty-system'),
           'XDG_CONFIG_HOME': str(work / 'config'), 'XDG_DATA_HOME': str(work / 'data'),
           'XDG_RUNTIME_DIR': str(work / 'runtime'), 'XDG_CACHE_HOME': str(work / 'cache'),
           'GNUPGHOME': str(work / 'gpg')}
    for name in ('HOME', 'FLATPAK_USER_DIR', 'FLATPAK_SYSTEM_DIR', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME',
                 'XDG_RUNTIME_DIR', 'XDG_CACHE_HOME', 'GNUPGHOME'):
        Path(env[name]).mkdir(mode=0o700)

    def command(args, capture=False):
        return subprocess.run(args, check=True, env=env, cwd=work, timeout=1200, text=True,
                              stdout=subprocess.PIPE if capture else None).stdout

    def flatpak(*args, capture=False):
        return command(['flatpak', '--user', *args], capture=capture)

    # The official HTTPS descriptor imports Flathub's key into this new remote.
    flatpak('remote-add', '--from', 'flathub', 'https://flathub.org/repo/flathub.flatpakrepo')
    repo = installation / 'repo'
    config = configparser.ConfigParser(interpolation=None)
    config.read(repo / 'config', encoding='utf-8')
    policy = config['remote "flathub"']
    if not policy.getboolean('gpg-verify') or not policy.getboolean('gpg-verify-summary'):
        raise RuntimeError('Both commit and summary signature verification are required for the public platform')
    remote_commit = flatpak('remote-info', '--show-commit', '--commit=' + expected, 'flathub', ref,
                            capture=True).strip()
    if remote_commit != expected:
        raise RuntimeError('Flathub did not supply the reviewed runtime commit')
    flatpak('install', '--noninteractive', '--no-related', '--no-deps', 'flathub', ref)
    if flatpak('info', '--show-commit', ref, capture=True).strip() != expected:
        # Install deploys the current branch head. Update can select its exact
        # signed historical commit if the branch advanced since review.
        flatpak('update', '--noninteractive', '--no-related', '--no-deps', '--commit=' + expected, ref)
    commit = flatpak('info', '--show-commit', ref, capture=True).strip()
    location = Path(flatpak('info', '--show-location', ref, capture=True).strip())
    expected_location = installation / 'runtime' / PLATFORM / arch / BRANCH / expected
    if commit != expected or location.resolve(strict=True) != expected_location:
        raise RuntimeError('The deployed runtime ref, commit or location differs from the reviewed pin')
    signature = command(['ostree', '--repo=' + str(repo), 'show', '--gpg-verify-remote=flathub', commit], capture=True)
    if 'Good signature from ' not in signature:
        raise RuntimeError('No good Flathub commit signature in the independent OSTree verification')
    (work / 'signature.txt').write_text(signature)
    record = {'ref': ref, 'commit': commit, 'gpg_verify': True, 'gpg_verify_summary': True,
              'signature_sha256': hashlib.sha256(signature.encode()).hexdigest(),
              'metadata_sha256': hashlib.sha256((location / 'metadata').read_bytes()).hexdigest()}
    (work / 'verified.json').write_text(json.dumps(record, indent=2) + '\n')
    location, _ = deployment(expected_location)
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
        print('deployment=' + str(location), file=output)
    print(ref, commit, flush=True)


if __name__ == '__main__':
    acquire()
