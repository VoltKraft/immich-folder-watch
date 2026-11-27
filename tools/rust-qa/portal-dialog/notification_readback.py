"""Replay an installed Rust Flatpak's notification through the actual GNOME Shell."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

from notification_pixels import BODY, TITLE, check
from runtime_pin import COMMITS, PLATFORM, BRANCH

ROOT = Path(__file__).resolve().parents[3]
APP = 'org.example.IfwPortalDialog'


def read(path):
    return json.loads(path.read_bytes())


def calls(trace, backends, shell):
    """Match the exact app, ID, payload, backend and display for both D-Bus calls."""
    if not re.fullmatch(r':\d+\.\d+', shell):
        raise ValueError('Missing GNOME Shell bus identity')
    messages = re.split(r'(?=^(?:method call|signal) )', trace, flags=re.M)
    found = []
    for message in messages:
        if not message.startswith('method call '):
            continue
        header, *args = message.splitlines()
        values = [line.strip() for line in args]
        if values[:2] != [f'string "{APP}"', 'string "native-test"']:
            continue
        route = re.search(r' sender=(:\d+\.\d+) -> destination=(\S+) .* path=/org/gtk/Notifications; '
                          r'interface=org.gtk.Notifications; member=(\w+)$', header)
        if not route or route[1] not in backends or route[2] not in (shell, 'org.gtk.Notifications'):
            raise ValueError('The recorded method did not reach the private display from its portal backend')
        if route[3] == 'AddNotification':
            contents = ' '.join(values[2:])
            for field, expected in (('title', TITLE), ('body', BODY)):
                pattern = r'string "' + field + r'" variant\s+string "([^"]+)"'
                if re.findall(pattern, contents) != [expected]:
                    raise ValueError(f'The portal delivered a different {field}')
        found.append((route[1], route[3]))
    if len(found) != 2 or found != [(found[0][0], 'AddNotification'), (found[0][0], 'RemoveNotification')]:
        raise ValueError('Expected one submission and its withdrawal from the same backend')
    return found[0][0]


def verify(folder, binary, arch, revision, run, attempt):
    result, inputs = (read(folder / name) for name in ('results.json', 'inputs.json'))
    if (inputs['revision'], inputs['run'], inputs['attempt']) != (revision, run, attempt):
        raise ValueError('Unexpected native source revision or run')
    host = inputs.get('host', {})
    if (host.get('architecture') != arch or not host.get('kernel') or not re.fullmatch('[0-9a-f]{64}', host.get('host_match_key', ''))
            or (host.get('distribution'), host.get('version')) != ('ubuntu', '24.04')):
        raise ValueError('Unexpected or incomplete native Ubuntu host identity')
    sources = {**inputs.get('build', {}).get('sources', {}), **inputs.get('drivers', {})}
    required = {'tools/rust-qa/portal-dialog/' + name for name in (
        'Cargo.toml', 'Cargo.lock', 'build.py', 'src/main.rs', 'src/portal.rs', 'src/parent.rs', 'native.py',
        'displays.py', 'flatpak_fixture.py', 'runtime_pin.py', 'shell_services.py', 'notification_readback.py',
        'notification_pixels.py')}
    required.update('tools/rust-qa/performance/' + name for name in ('linux.py', 'session.py', 'x11.py'))
    required.add('rust/crates/safe-fs/Cargo.toml')
    if not required.issubset(sources):
        raise ValueError('Missing sender or desktop observation sources')
    required_binaries = {'/usr/bin/' + name for name in ('gnome-shell', 'flatpak', 'pipewire', 'wireplumber', 'gst-launch-1.0')}
    required_binaries.update('/usr/libexec/' + name for name in ('xdg-desktop-portal', 'xdg-desktop-portal-gtk',
                             'xdg-desktop-portal-gnome', 'xdg-document-portal', 'xdg-permission-store'))
    if not required_binaries.issubset(inputs['runtime']) or not all(
            re.fullmatch('[0-9a-f]{64}', inputs['runtime'][path]) for path in required_binaries):
        raise ValueError('Missing native desktop or portal executable identities')
    for path, digest in sources.items():
        expected = subprocess.check_output(['git', 'show', revision + ':' + path], cwd=ROOT)
        if sha256(expected).hexdigest() != digest:
            raise ValueError(f'Original source mismatch: {path}')
    image = binary.read_bytes()
    elf_machine = int.from_bytes(image[18:20], 'little')
    if (image[:6] != b'\x7fELF\x02\x01' or elf_machine != {'aarch64': 183, 'x86_64': 62}[arch]
            or f'host: {arch}-unknown-linux-gnu' not in inputs['build']['compiler'].splitlines()):
        raise ValueError('Wrong native sender architecture')
    steps = result['steps']
    digest = sha256(image).hexdigest()
    if not digest == inputs['build']['binary'] == steps['sender_sha256']:
        raise ValueError('The native compiled and installed senders differ')
    platform = inputs['platform']
    if (platform['ref'] != f'runtime/{PLATFORM}/{arch}/{BRANCH}' or platform['commit'] != COMMITS[arch]
            or steps['flatpak']['installed_ref'] != f'app/{APP}/{arch}/test' or steps['flatpak']['runtime'] != COMMITS[arch]
            or not re.fullmatch('[0-9a-f]{64}', steps['flatpak']['commit'])):
        raise ValueError('Different test Flatpak or native Platform')
    acquisition = platform['acquisition']
    if (acquisition['ref'] != platform['ref'] or acquisition['commit'] != platform['commit']
            or acquisition['gpg_verify'] is not True or acquisition['gpg_verify_summary'] is not True
            or acquisition['metadata_sha256'] != platform['metadata_sha256']):
        raise ValueError('Missing signed native runtime acquisition')
    shell = steps['shell_process']
    services = steps['services']
    if (result['backend'] != 'wayland' or result['app_identity'] != 'installed temporary Flatpak'
            or result['notification_receiver'] != 'GNOME Shell org.gtk.Notifications'
            or shell['pid'] != shell['compositor_pid'] or shell['pid'] <= 0 or shell['image'] != '/usr/bin/gnome-shell'
            or inputs['runtime']['/usr/bin/gnome-shell'] != shell['sha256']
            or services['notification_receiver'] != steps['gnome']['notification_provider']):
        raise ValueError('Missing the private native GNOME Shell display')
    for action, status in (('notify', 'NOTIFICATION_ACCEPTED'), ('withdraw', 'NOTIFICATION_WITHDRAWN')):
        expected = ['APPLICATION_FLATPAK ' + APP, status]
        # Flatpak 1.14 may also write verbose diagnostics to these command logs.
        lines = (folder / (action + '.log')).read_text().splitlines()
        if steps[action] != expected or [line for line in lines if line.startswith(('APPLICATION_FLATPAK', 'NOTIFICATION_'))] != expected:
            raise ValueError(f'Missing the installed sender response for {action}')
    if any(steps[name] is not True for name in ('capture_before', 'capture_notification_list', 'capture_after')):
        raise ValueError('The screen stream did not capture all three transitions')
    backend = calls((folder / 'gnome-notification-bus.log').read_text(),
                    (steps['gnome']['backend'], services['gtk']), services['notification_receiver'])
    return dict(revision=revision, run=run, attempt=attempt, architecture=arch, host=host, binary=digest,
                backend=backend, shell=shell, captures=check(folder))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('binary', type=Path)
    parser.add_argument('--arch', choices=COMMITS, required=True)
    for option in ('revision', 'run', 'attempt'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    result = verify(args.folder, args.binary, args.arch, args.revision, args.run, args.attempt)
    print(json.dumps(result, indent=2))
