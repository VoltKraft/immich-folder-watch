"""Publish complete Linux QA outputs and pin a generation for multi-file readers."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile


BUILD_FILES = ("gui-graph.json", "gui-compiler.jsonl", "gui-registry-sources.json",
               "release/native-gui-assessment", "release/native-gui-assessment.inputs.json")
NATIVE_FILES = ("build.json", "graph.json", "compiler.jsonl", "registry-sources.json", "gui-unit-tests.log")
VERSIONS = "gui-generations"
CURRENT = "gui-current"


@contextmanager
def writer(root):
    import fcntl

    root.mkdir(parents=True, exist_ok=True)
    with (root / ".gui-build.lock").open("ab") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _save(root, source, names, transfer):
    versions = root / VERSIONS
    versions.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=versions) as temporary:
        ready = Path(temporary)
        identity = {}
        for name in names:
            path = source / name
            dest = ready / name
            dest.parent.mkdir(exist_ok=True, parents=True)
            transfer(path, dest)
            with dest.open("rb") as stream:
                identity[name] = [stat.S_IMODE(os.fstat(stream.fileno()).st_mode),
                                  hashlib.file_digest(stream, "sha256").hexdigest()]
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        generation = versions / ("gen-" + digest)
        if not generation.exists():
            ready.rename(generation)
        return generation


def _link(path, target, temporary):
    staged = temporary / "pointer"
    staged.symlink_to(os.path.relpath(target, path.parent))
    staged.replace(path)


def _switch(root, generation):
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        _link(root / CURRENT, generation, Path(temporary))


def _layout(root, names):
    """Adopt existing individual files before replacing any of their public paths."""
    current = root / CURRENT
    if not current.is_symlink():
        legacy = [name for name in names if (root / name).is_file()]
        if legacy:
            _switch(root, _save(root, root, legacy, shutil.copy2))
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        for name in names:
            path = root / name
            target = current / name
            if path.is_symlink() and path.readlink() == Path(os.path.relpath(target, path.parent)):
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            _link(path, target, Path(temporary))


def publish(root, staging, names):
    """Call under writer(root). Retain prior generations for readers holding their paths."""
    generation = _save(root, staging, names, os.replace)
    _layout(root, names)
    _switch(root, generation)
    return generation


def _pin(root, names):
    root = Path(root).resolve(strict=True)
    if root.parent.name == VERSIONS:
        generation = root
    else:
        current = root / CURRENT
        if not current.is_symlink():
            with writer(root):
                if not current.is_symlink():
                    if not all((root / name).is_file() for name in names):
                        raise FileNotFoundError(f"No complete GUI publication at {root}")
                    _layout(root, names)
        generation = current.resolve(strict=True)
        if generation.parent != root / VERSIONS:
            raise ValueError(f"Unexpected GUI generation at {root}")
    if not all((generation / name).is_file() for name in names):
        raise ValueError(f"Incomplete GUI generation {generation}")
    return generation


def pin_build(root):
    return _pin(root, BUILD_FILES)


def pin_native(root):
    return _pin(root, NATIVE_FILES)
