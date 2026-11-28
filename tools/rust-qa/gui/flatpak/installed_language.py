"""Bind the actual Flatpak editor, proxy and app-private saved-language profile."""
from pathlib import Path
import json
import os
import re
import runpy
import subprocess
import sys
import time

APP = 'org.example.IfwGuiProbe'
SYSTEM = {'en': 'de_DE.UTF-8', 'de': 'en_US.UTF-8'}
MENU = {'en': ('Open GUI', 'Restart', 'Quit'), 'de': ('GUI öffnen', 'Neustart', 'Beenden')}
EDITOR = {'en': ('Filename', 'Password', 'Deutsch', 'Quit'), 'de': ('Dateiname', 'Kennwort', 'English', 'Beenden')}
COMPILER_RECEIPT = 'bfde3d81b0948a70d55221591ec3b57d3a7707a497d889d3758ccbdfbfd1fac0'
CANDIDATE_RECEIPT = 'c21f6d98033b6574cc887bc393bf0e7ea77a4845630c9be721acc21194d1d909'


def compiler_input(binary, receipt, area, arch, *, candidate=False):
    from run import sha
    binary, receipt = binary.resolve(strict=True), receipt.resolve(strict=True)
    if arch != 'x86_64' or not all(p.is_relative_to(area) for p in (binary, receipt)):
        raise ValueError('Use the original source-bound Fedora x64 GUI under artifacts/rust')
    if candidate:
        builder = Path(__file__).resolve().parents[1] / 'flatpak-accessibility/build.py'
        return runpy.run_path(str(builder))['verify_candidate'](binary, receipt, CANDIDATE_RECEIPT)
    if sha(receipt) != COMPILER_RECEIPT:
        raise ValueError('The native receipt differs from the reviewed startup compiler')
    evidence = receipt.parent
    native = json.loads(receipt.read_bytes())
    if (native['target'] != arch + '-unknown-linux-gnu' or sha(binary) != native['binarySha256']
            or sha(evidence / 'supply.json') != native['supplySha256']
            or sha(evidence / 'compiler.jsonl') != native['unitsSha256']
            or any(sha(evidence / 'project' / path) != digest for path, digest in native['sources'].items())):
        raise ValueError('The GUI, original compiler units or input files differ from the reviewed build')
    return binary, receipt, native['sources']


def seed(language, previous):
    from run import sha
    if Path.home() != Path('/tmp/home') or os.environ.get('FLATPAK_USER_DIR') != '/tmp/home/.local/share/flatpak':
        raise ValueError('Expected the private user installation')
    config = Path.home() / '.var/app' / APP / 'config/immich-folder-watch/config.yaml'
    if previous is None:
        if config.exists():
            raise ValueError('Expected an empty synthetic Flatpak user profile')
        config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    elif previous != (config, sha(config)):
        raise ValueError('The previous original configuration changed')
    config.write_text('localization:\n  language: ' + language + '\n', encoding='utf-8')
    return config, sha(config)


REFERENCES = {
    'de': ('view-1-0-wgpu.bgra', '74cdd813becedc76765d9279c34a5544669a00ae720360a2fdec1c43bb0ab8d6'),
    'en': ('view-1-1-wgpu.bgra', '26912314d09ed219f26a2ef27948dc703f343980e980a0a286b0a7d09a324626'),
}
# Each crop contains just the label glyphs at the original 100% layout.
REGIONS = [(8, 8, 102, 26), (8, 53, 102, 72), (14, 101, 105, 122), (14, 126, 105, 147)]


def reference_images(directory, area):
    from run import sha
    files = {language: directory / filename for language, (filename, _) in REFERENCES.items()}
    if not directory.is_relative_to(area) or any(sha(p) != REFERENCES[lang][1] for lang, p in files.items()):
        raise ValueError('Use the original reviewed 640 by 400 GPU reference frames')
    return files


def editor_pixels(xid, language, out):
    import gi
    gi.require_version('Gdk', '3.0')
    gi.require_version('GdkX11', '3.0')
    from gi.repository import Gdk, GdkX11
    from PIL import Image
    from run import sha
    from session import wait_for
    native = GdkX11.X11Window.foreign_new_for_display(Gdk.Display.get_default(), xid)
    if not native or (native.get_width(), native.get_height()) != (640, 400):
        raise ValueError('Expected the original 640 by 400 installed X11 window')
    refs = {}
    for key, (_, expected) in REFERENCES.items():
        path = Path('/references') / (key + '.bgra')
        if sha(path) != expected:
            raise ValueError('Mounted reference bytes differ')
        refs[key] = Image.frombytes('RGBA', (640, 400), path.read_bytes(), 'raw', 'BGRA').convert('L')

    def ink(image, box):
        values = list(image.crop(box).tobytes())
        low, high = min(values), max(values)
        if high - low < 25:
            return set()
        return {i for i, v in enumerate(values) if v > (low + high) / 2}

    other = 'en' if language == 'de' else 'de'
    masks = {key: [ink(frame, box) for box in REGIONS] for key, frame in refs.items()}
    screen = out / 'editor.png'

    def sample():
        pix = Gdk.pixbuf_get_from_window(native, 0, 0, 640, 400)
        if not pix:
            return None
        mode = 'RGBA' if pix.get_has_alpha() else 'RGB'
        frame = Image.frombytes(mode, (640, 400), bytes(pix.get_pixels()), 'raw', mode, pix.get_rowstride()).convert('L')
        rows = []
        for i, (label, box) in enumerate(zip(EDITOR[language], REGIONS, strict=True)):
            obs = ink(frame, box)
            correct, opposite = masks[language][i], masks[other][i]
            match = len(obs & correct) / len(obs | correct)
            control = len(obs & opposite) / len(obs | opposite)
            rows.append({'label': label, 'box': box, 'actualInk': len(obs), 'referenceInk': len(correct),
                         'expectedOverlap': match, 'oppositeOverlap': control})
        pix.savev(str(screen), 'png', [], [])
        (out / 'glyphs.json').write_text(json.dumps(rows, indent=2) + '\n')
        if all(row['expectedOverlap'] == 1 and row['oppositeOverlap'] < 1 for row in rows):
            return {'pixelsSha256': sha(screen), 'controls': rows,
                    'referenceSha256': REFERENCES[language][1], 'oppositeReferenceSha256': REFERENCES[other][1]}
        return None

    return wait_for(sample, 5, 'Installed editor glyphs do not match the expected original frames')


def readback(language, before, xid, bus, dbus_call, out, *, screen_reader=False):
    from run import sha
    import tray_menu
    gui = before['gui']['pid']
    proc = Path('/proc') / str(gui)
    keys = {b'XDG_CONFIG_HOME', b'LC_ALL', b'FLATPAK_ID'}
    env = {}
    for value in (proc / 'environ').read_bytes().split(b'\0'):
        key, _, val = value.partition(b'=')
        if key in keys:
            env[key.decode()] = val.decode()
    config_home = Path('/tmp/home/.var/app') / APP / 'config'
    if (env.get('XDG_CONFIG_HOME') != str(config_home) or env.get('FLATPAK_ID') != APP
            or env.get('LC_ALL') != SYSTEM[language]):
        raise ValueError(f'The installed GUI did not receive the intended app-private configuration and locale: {env}')
    path = config_home / 'immich-folder-watch/config.yaml'
    seen = proc / 'root' / path.relative_to('/')
    if not seen.samefile(path):
        raise ValueError('The sandbox and private desktop do not refer to the same original configuration file')
    editor = editor_pixels(xid, language, out)
    menu = {}
    tray_menu.read_layout(bus, dbus_call, menu, MENU[language])
    if menu['revision'] != 1:
        raise ValueError('The installed primary changed languages before its first tray readback')
    stat = seen.stat()
    return {'saved': language, 'environment': env, 'configPath': str(path), 'configSha256': sha(seen),
            'configDevice': stat.st_dev, 'configInode': stat.st_ino,
            **({} if screen_reader else {'accessibility': accessible_editor(language, proc, gui)}),
            'guiPid': gui, 'xid': xid, 'editor': editor, 'tray': menu}


def registry_connection(stack, bus):
    from desktop_input import Gio, GLib, start_accessibility
    enabled = start_accessibility(stack)
    address, = bus.call_sync('org.a11y.Bus', '/org/a11y/bus', 'org.a11y.Bus', 'GetAddress', None,
                             GLib.VariantType.new('(s)'), Gio.DBusCallFlags.NONE, 3000, None).unpack()
    flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
    peer = Gio.DBusConnection.new_for_address_sync(address, flags, None, None)
    stack.callback(peer.close_sync, None)
    return enabled, address, peer


def accessibility_control(stack, dbus_call, out, enabled, address, peer):
    from desktop_input import Atspi, nodes
    from session import checked_start, stop, wait_for
    # A native GTK button establishes whether this same private bus delivers real accessible controls.
    control = checked_start(stack, [sys.executable, '-B', '/app/flatpak/installed_language.py', '--accessibility-peer'],
                            out / 'accessibility-control.log')

    def exposed():
        return any(n.get_process_id() == control.pid and n.get_role() == Atspi.Role.PUSH_BUTTON
                   and n.get_name() == 'Private accessibility control' for n in nodes(control.pid))

    wait_for(exposed, 8, 'The native GTK positive control did not reach the private accessibility registry')
    registry = dbus_call(peer, 'GetNameOwner', 'org.a11y.atspi.Registry')
    result = {'enabled': enabled(), 'address': address, 'registryOwner': registry,
              'registryPid': dbus_call(peer, 'GetConnectionUnixProcessID', registry),
              'gtkPid': control.pid, 'observedButton': 'Private accessibility control'}
    stop(control)
    return result


def sandbox_accessibility(commit, out):
    from flatpak_fixture import LAUNCH_BUS
    script = Path(__file__).with_name('accessibility-readback.sh').read_text()
    # Feed the observer over stdin to the existing runtime shell after both GUIs have quit.
    # Using the same installed ref preserves its normal session and accessibility bus proxies.
    cmd = ['flatpak', 'run', '--user', '--branch=test', '--command=sh', APP, '-s']
    run = subprocess.run(cmd, input=script, text=True, capture_output=True, timeout=20,
                         env={**os.environ, 'DBUS_SYSTEM_BUS_ADDRESS': LAUNCH_BUS})
    (out / 'sandbox-accessibility.log').write_text(run.stdout + run.stderr)
    run.check_returncode()
    header, _, _ = run.stdout.partition('BEGIN ')
    fields = dict(row.split('=', 1) for row in header.splitlines())
    if fields['app-commit'] != commit or not fields['instance-id'].isdigit():
        raise ValueError('The runtime bus probe did not execute in the same installed Flatpak ref')
    matches = re.findall(r'^BEGIN (\w+)\n(.*?)^END \1 (\d+)$', run.stdout, re.M | re.S)
    if [name for name, _, _ in matches] != ['enabled', 'address', 'registry', 'events']:
        raise ValueError('Incomplete runtime accessibility readback')
    return {'instance': fields['instance-id'], 'commit': commit, 'runtimeGdbus': fields['gdbus'],
            'sessionBus': fields['DBUS_SESSION_BUS_ADDRESS'], 'accessibilityBus': fields['AT_SPI_BUS_ADDRESS'],
            'queries': {name: {'exit': int(status), 'reply': body.strip()} for name, body, status in matches}}


def accessible_editor(language, proc, gui):
    from desktop_input import Atspi, GLib, nodes
    deadline = time.monotonic() + 2
    apps = {}
    while time.monotonic() < deadline:
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)
        desktop = Atspi.get_desktop(0)
        for index in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(index)
            if app and app.get_role() == Atspi.Role.APPLICATION:
                pid = app.get_process_id()
                labels = sorted({n.get_name() for n in nodes(pid) if n.get_name() in EDITOR[language]})
                apps[pid] = {'name': app.get_name(), 'labels': labels}
        if gui in apps and set(apps[gui]['labels']) == set(EDITOR[language]):
            break
        time.sleep(.1)
    return {'observedApplications': apps,
            'allEditorLabelsObserved': gui in apps and set(apps[gui]['labels']) == set(EDITOR[language]),
            'sandboxAtspiSocketPresent': (proc / 'root/run/flatpak/at-spi-bus').is_socket()}


if __name__ == '__main__' and sys.argv[1:] == ['--accessibility-peer']:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    window = Gtk.Window(title='Private accessibility control')
    window.add(Gtk.Button(label='Private accessibility control'))
    window.show_all()
    Gtk.main()
