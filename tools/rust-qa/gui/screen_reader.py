"""Run the native Orca, Speech Dispatcher and eSpeak stack on a private audio sink."""

import hashlib
import errno
import os
from pathlib import Path
import pty
import re
import subprocess
import threading
import tty

from session import checked_start, check_alive, wait_for


LABELS = {"Dateiname": r"Dateiname entry", "Kennwort": r"Kennwort password text",
          "English": r"English (?:push )?button", "Filename": r"Filename entry"}


def announces(utterance, label):
    return bool(re.match(LABELS[label] + r"(?:[.\s]|$)", utterance))


def live_debug(stack, destination):
    # Orca 46 block-buffers regular debug files. A private terminal makes each
    # emitted line visible before the next focus gesture; retain its complete output.
    master, slave = pty.openpty()
    tty.setraw(slave)
    def drain():
        with os.fdopen(master, "rb", buffering=0) as source, destination.open("xb", buffering=0) as log:
            try:
                while chunk := source.read(65536):
                    log.write(chunk)
            except OSError as error:
                if error.errno != errno.EIO:  # last slave closed
                    raise
    worker = threading.Thread(target=drain, daemon=True)
    worker.start()
    stack.callback(worker.join, 3)
    stack.callback(os.close, slave)
    return os.ttyname(slave)


class ScreenReader:
    def __init__(self, stack):
        self.debug = Path("/qa/orca-debug.log")
        self.audio = Path("/qa/orca-audio.raw")
        self.log = Path("/qa/orca-launch.log")
        config = Path("/tmp/private-speech")
        modules = config / "modules"
        modules.mkdir(parents=True)
        (modules / "espeak-ng.conf").write_text("# Private eSpeak fixture using module defaults.\n")
        (config / "speechd.conf").write_text(
            'LogLevel 5\nAudioOutputMethod "alsa"\nAudioALSADevice "ifwfile"\n'
            'AddModule "espeak-ng" "sd_espeak-ng" "espeak-ng.conf"\nDefaultModule "espeak-ng"\n')
        alsa = config / "alsa.conf"
        alsa.write_text('pcm.null { type null }\n'
                        'pcm.ifwfile { type file slave.pcm "null" file "/qa/orca-audio.raw" format "raw" }\n')
        socket = config / "speech.sock"
        os.environ.update(ALSA_CONFIG_PATH=str(alsa), SPEECHD_ADDRESS=f"unix_socket:{socket}",
                          GSETTINGS_BACKEND="memory")
        dispatcher_log = Path("/qa/speechd.log")
        dispatcher = checked_start(stack, ["speech-dispatcher", "-s", "-t", "0", "-c", "unix_socket",
            "-S", str(socket), "-C", str(config), "-P", str(config / "pid"), "-L", str(config)], dispatcher_log)
        wait_for(lambda: check_alive(dispatcher, dispatcher_log) or socket.is_socket(), 8,
                 "The private speech server did not start")
        self.version = subprocess.check_output(["orca", "--version"], text=True, timeout=8).strip()
        reader_command = []
        self.modifier_display = None
        if self.version.split()[-1] == "46.1" and os.environ.get("WAYLAND_DISPLAY") == "ifw-test" and "DISPLAY" not in os.environ:
            # Orca 46.1 unconditionally runs xkbcomp on DISPLAY. Only its own process sees
            # the private X server already created by this fixture. The editor uses Mutter.
            self.modifier_display = ":93"
            reader_command = ["env", "DISPLAY=:93", "GDK_BACKEND=wayland"]
        self.orca = checked_start(stack, [*reader_command, "orca", "--speech-system", "speechdispatcherfactory",
                                         "--debug-file", live_debug(stack, self.debug)], self.log)
        self.utterances = []
        self.position = 0
        self.wait_for_speech()

    def spoken(self):
        check_alive(self.orca, self.log)
        if self.debug.is_file():
            with self.debug.open("rb") as stream:
                stream.seek(self.position)
                chunk = stream.read()
                complete = chunk.rfind(b"\n") + 1
                for line in chunk[:complete].decode("utf-8", errors="replace").splitlines():
                    match = re.search(r"SPEECH DISPATCHER: Speaking '(.*?)' as (?:string|char|key)\b", line)
                    if match:
                        self.utterances.append(match.group(1))
                self.position += complete
        return self.utterances

    def wait_for_speech(self):
        return wait_for(lambda: self.spoken(), 15, "Orca did not send speech to its private synthesizer")

    def begin(self):
        # Establish a known focus before the measured traversal. Orca 46 can discover the
        # first focused widget while processing the initial Tab, without announcing it.
        self.wait_label("English", 0)
        self.start = len(self.utterances)
        self.audio_start = self.audio.stat().st_size if self.audio.is_file() else 0

    def wait_label(self, label, offset=None):
        start = self.start if offset is None else offset
        return wait_for(lambda: next((i+1 for i, s in enumerate(self.spoken()[start:], start)
                                      if announces(s, label)), None), 8, f"Orca did not announce {label}") - 1

    def result(self):
        indices = []
        for label in LABELS:
            indices.append(self.wait_label(label, indices[-1] + 1 if indices else self.start))
        password_speech = self.utterances[indices[1] + 1:indices[2]]
        if password_speech.count("•") != 3 or any(
                re.search(r"\b(?:x|y|z|xy|xyz)\b", spoken, re.IGNORECASE) for spoken in password_speech):
            raise RuntimeError("Orca did not mask all three synthetic password keystrokes")
        wait_for(lambda: self.audio.exists() and self.audio.stat().st_size > self.audio_start + 8192, 8,
                 "The synthesizer did not produce samples for the private ALSA sink")
        samples = self.audio.read_bytes()
        if not any(samples[self.audio_start:]):
            raise RuntimeError("The private ALSA sink received silence")
        return {"backend": "Orca / Speech Dispatcher / eSpeak NG / ALSA file",
                "orcaVersion": self.version, "orcaModifierDisplay": self.modifier_display,
                "spoken": self.utterances[self.start:], "protectedFieldSpeech": password_speech,
                "audioStartOfTraversal": self.audio_start, "audioBytesObserved": len(samples),
                "audioPrefixSha256": hashlib.sha256(samples).hexdigest()}
