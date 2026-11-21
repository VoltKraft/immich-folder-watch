"""Run the existing private Intel-to-software Wayland recovery scenario and measure subsequent idle."""

import argparse
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "graphics"))
import probe


def observe(name, subject):
    freeze_graphics = probe.freeze_drivers

    def with_idle_observer(destination):
        sources = freeze_graphics(destination)
        key = Path("tools/rust-qa/graphics/scenarios.py")
        original = key.with_name("original_scenarios.py")
        (destination / key).rename(destination / original)
        sources[original.as_posix()] = sources.pop(key.as_posix())
        shutil.copyfile(HERE / "idle.py", destination / key)
        sources[key.as_posix()] = probe.sha(destination / key)
        return sources

    # The unmodified runner snapshots its inside drivers and verifies their hashes
    # after the trial. The added observer calls the original scenario before sampling.
    probe.freeze_drivers = with_idle_observer
    try:
        args = argparse.Namespace(name=name, subject=subject, backend="wayland", case="recover",
                                  driver="intel-and-mesa", integrated=True, diagnostic_mailbox=False,
                                  monitor_capture=True, trace_waits=True)
        probe.launch(args)
    finally:
        probe.freeze_drivers = freeze_graphics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Fresh evidence directory label")
    parser.add_argument("--subject", type=Path, required=True, help="Verified integrated graphics subject directory")
    args = parser.parse_args()
    observe(args.name, args.subject)
