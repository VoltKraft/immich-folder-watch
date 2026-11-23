"""Drive a separate, source-bound native PE with the existing root-repaint dispatch workload."""
from contextlib import ExitStack
from functools import partial
import json
import os
import shutil

import prepare
import readback
from frame_latency import measured_generation
from inputs import recorder, sha
from scan_present import start


def prepare_subject(base, out, budget, record):
    if record["target"] != prepare.TARGET:
        raise ValueError("This diagnostic measures the native x64 regression")
    record["pairedBinary"] = record["binary"]
    record["pair"] = readback.pair(base, record)
    record["diagnosticInputs"] = readback.inputs()
    shutil.copyfile(budget, out / "reference-budget.json")
    recorder.write(out / "result.json", record)
    exe = prepare.build(out, base, record)
    diagnostic = out / "diagnostic.exe"
    shutil.copyfile(exe, diagnostic)
    record["binary"] = sha(diagnostic)
    if record["binary"] == record["pairedBinary"] or recorder.pe_machine(diagnostic) != 0x8664:
        raise ValueError("Expected the separately linked native x64 measurement executable")
    record["diagBuildSha256"] = sha(out / "diagnostic-build.json")
    recorder.write(out / "result.json", record)
    return diagnostic


def measure(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record):
    if not files:
        raise ValueError("Frame cost requires the native inventory observer")
    trial = readback.TRIAL
    try:
        with ExitStack() as scope:
            for key, value in (("IFW_QA_WINDOWS_DISPATCH", "1"), ("IFW_QA_WINDOWS_FRAME_COST", "1"),
                               ("IFW_QA_WINDOWS_SINGLE_WAKE", "0"), ("IFW_QA_WINDOWS_HIDDEN_PAINT_CONTROL", "0")):
                os.environ[key] = value
                scope.callback(os.environ.pop, key)
            scan = recorder.measure_scan(api, fixture, "rust", gui, files, area / trial, endpoint, user_sid, out,
                                         recorder.await_value, recorder.stop_subject, recorder.p95, token,
                                         presentation_trace=partial(start, api, present, "Mailbox"))
    finally:
        record["raw"] = {trial + suffix:sha(out / (trial + suffix)) for suffix in readback.RAW
                         if (out / (trial + suffix)).is_file()}
    record["scan"] = scan
    recorder.write(out / "result.json", record)
    scan["device"] = measured_generation(out / (trial + ".log"), "Mailbox", dispatch_trace=True)
    record["cost"] = readback.recalculate(out, record)
    recorder.write(out / "result.json", record)
