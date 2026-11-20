"""Run the native Orca, Speech Dispatcher and eSpeak stack on a private audio sink."""

import hashlib
import os
from pathlib import Path
import re

from session import checked_start, check_alive, wait_for


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
        self.orca = checked_start(stack, ["orca", "--speech-system", "speechdispatcherfactory",
                                         "--debug-file", str(self.debug)], self.log)
        self.utterances = []
        self.position = 0
        self.wait_for_speech()

    def spoken(self):
        check_alive(self.orca, self.log)
        if self.debug.is_file():
            with self.debug.open(encoding="utf-8", errors="replace") as stream:
                stream.seek(self.position)
                for line in stream:
                    match = re.search(r"SPEECH DISPATCHER: Speaking '(.*?)' as (?:string|char)", line)
                    if match:
                        self.utterances.append(match.group(1))
                self.position = stream.tell()
        return self.utterances

    def wait_for_speech(self):
        return wait_for(lambda: self.spoken(), 15, "Orca did not send speech to its private synthesizer")

    def result(self):
        expected = ("Dateiname entry", "Kennwort password text", "English button", "Filename entry")
        def complete():
            utterances = self.spoken()
            return all(any(label in spoken for spoken in utterances) for label in expected)
        wait_for(complete, 8, "The screen reader did not announce all four focused labels")
        indices = [next(i for i, spoken in enumerate(self.utterances) if label in spoken) for label in expected]
        if indices != sorted(indices):
            raise RuntimeError("Orca announced the focused controls in a different order")
        password_speech = self.utterances[indices[1] + 1:indices[2]]
        if password_speech.count("•") != 3 or any(
                re.search(r"\b(?:x|y|z|xy|xyz)\b", spoken, re.IGNORECASE) for spoken in password_speech):
            raise RuntimeError("Orca did not mask all three synthetic password keystrokes")
        wait_for(lambda: self.audio.exists() and self.audio.stat().st_size > 8192, 8,
                 "The synthesizer did not produce samples for the private ALSA sink")
        samples = self.audio.read_bytes()
        if not any(samples):
            raise RuntimeError("The private ALSA sink received silence")
        return {"backend": "Orca / Speech Dispatcher / eSpeak NG / ALSA file",
                "spoken": self.utterances, "protectedFieldSpeech": password_speech, "audioBytesObserved": len(samples),
                "audioPrefixSha256": hashlib.sha256(samples).hexdigest()}
