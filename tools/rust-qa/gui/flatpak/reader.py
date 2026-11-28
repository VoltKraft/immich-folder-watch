"""Read the installed GUI through its actual AT-SPI proxy and follow Orca on X11."""
import hashlib
import re
import time
from pathlib import Path

from desktop_input import Atspi, Gio, GLib, nodes, tap
from installed_language import EDITOR
from native import X11Observer
from screen_reader import ScreenReader
from session import wait_for

REGISTRY = 'org.a11y.atspi.Registry'


def registry_call(bus, path, interface, method):
    result, = bus.call_sync(REGISTRY, '/org/a11y/atspi/' + path, 'org.a11y.atspi.' + interface,
                            method, None, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()
    return result


def process_id(bus, name):
    pid, = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                         'GetConnectionUnixProcessID', GLib.Variant('(s)', (name,)), None,
                         Gio.DBusCallFlags.NONE, 2000, None).unpack()
    return pid


def roots(bus):
    return [{'name': name, 'path': path, 'busPid': process_id(bus, name)}
            for name, path in registry_call(bus, 'accessible/root', 'Accessible', 'GetChildren')]


def events(bus):
    return registry_call(bus, 'registry', 'Registry', 'GetRegisteredEvents')


def without_bus(primary):
    gui = Path('/proc') / str(primary['gui']['pid'])
    addresses = [s.decode() for s in (gui / 'environ').read_bytes().split(b'\0')
                 if s.startswith(b'AT_SPI_BUS_ADDRESS=')]
    socket = (gui / 'root/run/flatpak/at-spi-bus').exists()
    if addresses or socket:
        raise ValueError('Expected a normal launch without an advertised accessibility socket')
    return {'addresses': addresses, 'socketPresent': socket}


def without_reader(bus, primary):
    samples = []
    for _ in range(3):
        time.sleep(.3)
        samples.append({'listeners': events(bus), 'roots': roots(bus)})
    if any(row['listeners'] for row in samples):
        raise ValueError('Expected a registry without registered event listeners before starting Orca')
    return {'samples': samples, 'guiPid': primary['gui']['pid'], 'proxyPid': primary['proxy']['pid']}


class InstalledReader:
    def __init__(self, stack, bus, display, mode):
        self.bus = bus
        self.keyboard = X11Observer(display)
        self.mode = mode
        self.orca = ScreenReader(stack)
        def orca_listeners():
            return [(name, event) for name, event in events(bus) if process_id(bus, name) == self.orca.orca.pid]
        self.events = wait_for(orca_listeners, 5, 'Orca did not register accessibility listeners')

    def measure(self, report, language, primary, xid):
        gui, proxy = primary['gui']['pid'], primary['proxy']['pid']
        expected = EDITOR[language]
        report.update(proxyPid=proxy, guiPid=gui, xid=xid, orcaPid=self.orca.orca.pid,
                      orcaVersion=self.orca.version, listeners=self.events)
        if self.keyboard.poll() != xid:
            raise ValueError('The installed editor no longer owns the original XID')
        self.keyboard.focus_for_input()

        def read():
            found = [p for p in roots(self.bus) if p['busPid'] == proxy]
            if not found:
                return []
            if len(found) != 1:
                raise ValueError('The installed proxy registered several application roots')
            root, = found
            desktop = Atspi.get_desktop(0)
            for index in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(index)
                if app and app.app.bus_name == root['name'] and app.path == root['path']:
                    pid = app.get_process_id()
                    rows = [{'name': n.get_name(), 'role': n.get_role_name(),
                             'focused': n.get_state_set().contains(Atspi.StateType.FOCUSED)}
                            for n in nodes(pid) if n.app and n.app.bus_name == root['name'] and n.get_name() in expected]
                    report.update(root=root, toolkit=app.get_toolkit_name(), application=app.get_name(),
                                  accessibleReportedPid=pid, controls=rows)
                    return rows
            return []

        # Read the original GUI while only its proxy and native executable are alive.
        from run import save
        out = Path('/qa') / language
        offset = len(self.orca.spoken())
        audio_start = self.orca.audio.stat().st_size if self.orca.audio.exists() else 0
        if self.mode == 'stock':
            seen = []
            for _ in range(4):
                tap(self.keyboard, 0xff09)
                time.sleep(.35)
                seen.extend(read())
            report.update(controls=seen, roots=roots(self.bus), speech=self.orca.spoken()[offset:])
            save(out / 'reader.json', report)
            if seen or any(label in s for label in expected for s in report['speech']):
                raise ValueError('The original installed control exposed localized controls to the reader')
            return

        def complete():
            rows = read()
            roles = ({'entry', 'text'}, {'password text'}, {'push button', 'button'}, {'push button', 'button'})
            return all(any(row['name'] == label and row['role'] in accepted for row in rows)
                       for label, accepted in zip(expected, roles, strict=True))

        try:
            wait_for(complete, 8, 'The installed AT-SPI peer did not expose four typed editor controls')
            if self.mode == 'ordinary':
                # Orca 46 can discover the initial focus without announcing the first Tab.
                # Start measuring after it has spoken the actual window's final button.
                for _ in range(6):
                    if any(row['focused'] and row['name'] == expected[-1] for row in read()):
                        break
                    tap(self.keyboard, 0xff09)
                    time.sleep(.12)
                else:
                    raise ValueError('Could not position focus on the original installed Quit button')
                report['initialSpeech'] = wait_for(lambda: next((s for s in self.orca.spoken()[offset:]
                    if re.match(re.escape(expected[-1]) + r'(?:[.\s]|$)', s)), None), 8,
                    'Orca did not announce the installed Quit button before traversal')
                offset = len(self.orca.spoken())
                audio_start = self.orca.audio.stat().st_size if self.orca.audio.exists() else 0
            visited = []
            for _ in range(5):
                # Establish the speech offset before the physical focus change.
                speech_start = len(self.orca.spoken())
                before = next((r['name'] for r in read() if r['focused']), None)
                tap(self.keyboard, 0xff09)
                def next_focus():
                    return next((r['name'] for r in read() if r['focused'] and r['name'] != before), None)
                label = wait_for(next_focus, 3, 'Tab did not move focus on the original installed editor')
                def utterance():
                    return next((s for s in self.orca.spoken()[speech_start:]
                                 if re.match(re.escape(label) + r'(?:[.\s]|$)', s)), None)
                spoken = wait_for(utterance, 8, f'Orca did not announce the newly focused {label}')
                visited.append({'label': label, 'utterance': spoken})
                report['focus'] = visited
                if {r['label'] for r in visited} == set(expected):
                    break
            if {r['label'] for r in visited} != set(expected):
                raise ValueError('Orca did not follow all four localized controls')
            wait_for(lambda: self.orca.audio.exists() and self.orca.audio.stat().st_size > audio_start + 8192,
                     8, 'The private synthesizer did not produce audio during the focus traversal')
            samples = self.orca.audio.read_bytes()[audio_start:]
            if not any(samples):
                raise ValueError('The private synthesizer produced silence')
            report.update(audioStart=audio_start, audioBytes=len(samples), audioSha256=hashlib.sha256(samples).hexdigest())
        finally:
            report['speech'] = self.orca.spoken()[offset:]
            report['roots'] = roots(self.bus)
            save(out / 'reader.json', report)
