"""Verify three independent Intel-to-software recovery records and their bounded idle intervals."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "graphics"))
from probe import verify_surface_modes


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def trial(directory):
    receipt = json.loads((directory / "inputs.json").read_text())
    result = json.loads((directory / "results.json").read_text())
    build = json.loads((directory / "build.json").read_text())
    if (receipt["observer_exit"] != 0 or receipt["observation_sha256"] != sha(directory / "results.json")
            or receipt["build_receipt_sha256"] != sha(directory / "build.json")
            or result["gui_sha256"] != build["binary_sha256"]):
        raise ValueError(f"Source-bound successful observation required in {directory}")
    if (result["case"] != "recover" or result["backend"] != "wayland" or result["driver"] != "intel-and-mesa"
            or result["diagnostic_mailbox"] or result["mesa_present_mode"] is not None
            or result["exposed_drm"] != ["renderD128"] or result["exit"] != 0):
        raise ValueError("Expected the ordinary Wayland presentation policy on the isolated render node")
    lines = result["app_lines"]
    adapters = [line.split()[2] for line in lines if line.startswith("ADAPTER Vulkan ")]
    policy = verify_surface_modes(lines, "wayland", adapters, build["sources"]["tools/rust-qa/gui/src/graphics.rs"])
    if (adapters != ["IntegratedGpu", "Cpu"] or result["surface_policy"] != policy
            or [row["requested"] for row in policy["generations"]] != ["Mailbox", "Mailbox"]):
        raise ValueError("Expected a supported Mailbox request on both observed generations")
    if (result["retained_draft"] != "rw02" or not result["restored_editor_focus"]
            or result["post_recovery_edit_damage"] < 1 or result["monitor_output"]["frames_during_keyboard"] < 2
            or result["background_after_failure"]["worker"] != result["initial_worker"]
            or result["background_after_failure"]["directory_reads"] < 1 or result["stationary_control"]["role"] != "button"):
        raise ValueError("Missing post-loss input, drawing, worker activity or stationary focus")
    for name, limit in (("visible", 1), ("hidden", 0)):
        interval = result[name + "_idle_after_recovery"]
        if interval["seconds"] < 15 or not 0 <= interval["root_buffer_commits"] <= limit:
            raise ValueError(f"Invalid {name} idle observation")
    return result["gui_sha256"], result["worker_sha256"], result["initial_worker"]["start_ticks"]


def verify(directories):
    if len({p.resolve() for p in directories}) != 3:
        raise ValueError("Three distinct native session directories are required")
    records = [trial(path) for path in directories]
    if len({r[:2] for r in records}) != 1 or len({r[2] for r in records}) != 3:
        raise ValueError("Use one GUI and worker build across three distinct process lifetimes")
    print(f"Verified three native Intel-to-software Wayland recoveries for {records[0][0]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs=3, type=Path)
    verify(parser.parse_args().directories)
