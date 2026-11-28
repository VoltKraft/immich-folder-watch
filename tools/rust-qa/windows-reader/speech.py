"""Read only NVDA speech output and record the expected synthetic announcements."""

import re


SPEECH_HEADER = re.compile(r"^IO - speech\.(?:speech\.)?speak \(")
MASK = re.compile(r"['\"](?:\*|•|asterisk|star|bullet)['\"]", re.IGNORECASE)
CLEAR = re.compile(r"['\"](?:[xyz]{1,3}|[xyz](?: [xyz]){1,2})['\"]", re.IGNORECASE)
EXPECTED = ("Dateiname", "Kennwort", "mask-1", "mask-2", "mask-3", "English", "Filename")
PASS_NEXT_KEY = re.compile(r"""(['"])Pass next key through\1""")


class Speech:
    def __init__(self, cues):
        self.cues = cues
        self.observed = []
        self.utterances = 0
        self.speech_header = False
        self.pass_key_announced = False

    def line(self, text):
        if not self.speech_header or not text.startswith("Speaking ["):
            self.speech_header = bool(SPEECH_HEADER.match(text))
            return
        self.speech_header = False
        self.utterances += 1
        if "Kennwort" in self.observed and "English" not in self.observed and CLEAR.search(text):
            raise ValueError("The reader spoke a clear synthetic password character")
        if len(self.observed) == len(EXPECTED):
            if (not self.pass_key_announced and (self.cues / "request-pass-key").is_file()
                    and PASS_NEXT_KEY.search(text)):
                self.pass_key_announced = True
                (self.cues / "pass-key-announced").touch(exist_ok=False)
            return
        expected = EXPECTED[len(self.observed)]
        found = MASK.search(text) if expected.startswith("mask-") else re.search(r"\b" + expected + r"\b", text)
        if found:
            self.observed.append(expected)
            (self.cues / expected).touch(exist_ok=False)


class LogTail:
    def __init__(self, path, speech):
        self.path = path
        self.speech = speech
        self.position = 0
        self.pending = b""
        self.synth = None
        self.initialized = False
        self.diagnostics = []

    def read(self):
        if not self.path.is_file():
            return
        length = self.path.stat().st_size
        if length < self.position or length > 16 * 1024 * 1024:
            raise ValueError("Unexpected private NVDA log size")
        with self.path.open("rb") as stream:
            stream.seek(self.position)
            data = stream.read(length - self.position)
        self.position += len(data)
        lines = (self.pending + data).split(b"\n")
        self.pending = lines.pop()
        for raw in lines:
            text = raw.decode("utf-8-sig", errors="replace").rstrip("\r")
            module = re.match(r"^(WARNING|ERROR|CRITICAL) - ([\w.<>]+) \(", text)
            if module and len(self.diagnostics) < 30:
                self.diagnostics.append(list(module.groups()))
            match = re.fullmatch(r"Loaded synthDriver ([\w-]+)", text)
            if match:
                self.synth = match[1]
            if text.startswith("NVDA initialized"):
                self.initialized = True
            self.speech.line(text)
