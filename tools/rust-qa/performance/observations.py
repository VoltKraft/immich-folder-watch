"""Process-independent directory access and optional instrumented frame counts."""

import ctypes
import os
import select
import struct
import threading
import time


class DirectoryReads:
    """Record when the subject enumerates the synthetic leaf directories via Linux inotify."""

    def __init__(self, stack, tree):
        libc = ctypes.CDLL(None, use_errno=True)
        libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        descriptor = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if descriptor < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1")
        stack.callback(os.close, descriptor)
        self.count = 0
        for directory in tree.iterdir():
            if libc.inotify_add_watch(descriptor, os.fsencode(directory), 0x01000001) < 0:  # IN_ONLYDIR | IN_ACCESS
                raise OSError(ctypes.get_errno(), "inotify_add_watch")
            self.count += 1
        self.events = []
        self.overflow = False
        stopped = threading.Event()

        def observe():
            while not stopped.is_set():
                if not select.select([descriptor], [], [], .05)[0]:
                    continue
                data = os.read(descriptor, 65536)
                observed = time.monotonic()
                position = 0
                while position < len(data):
                    watch, mask, _, name_length = struct.unpack_from("=iIII", data, position)
                    position += 16 + name_length
                    if mask & 0x4000:  # IN_Q_OVERFLOW
                        self.overflow = True
                    if name_length == 0 and mask & 0x1:
                        self.events.append((observed, watch))

        reader = threading.Thread(target=observe, daemon=True)
        reader.start()
        stack.callback(reader.join)
        stack.callback(stopped.set)

    def scan_bounds(self, start, end):
        events = [(seen, watch) for seen, watch in self.events if start <= seen <= end]
        directories = len({watch for _, watch in events})
        if self.overflow or directories != self.count:
            raise RuntimeError(f"Observed directory reads in {directories} of {self.count} fixture directories")
        return events[0][0], events[-1][0], directories


class Frames:
    """The subject writes R when the counter is attached and F once per rendered target frame."""

    def __init__(self, stack):
        self.reader, self.writer = os.pipe2(os.O_CLOEXEC)
        os.set_blocking(self.reader, False)
        stack.callback(os.close, self.reader)
        stack.callback(os.close, self.writer)
        self.ready = False
        self.total = 0

    def read(self):
        while True:
            try:
                data = os.read(self.reader, 65536)
            except BlockingIOError:
                break
            if not data:
                break
            if any(value not in b"RF" for value in data):
                raise RuntimeError("Invalid frame counter event")
            self.ready |= b"R" in data
            self.total += data.count(b"F")
        return self.total
