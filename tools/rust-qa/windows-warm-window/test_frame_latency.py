"""Exercise depth, HWND, pixel and WPF-budget attribution with synthetic observer records."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from frame_latency import HOST_BUILD, measured_generation, paired_frame_latency, visible_edits
from inputs import QA, TWO_FRAME_EDIT, recorder, sha
from metrics import METRICS
from scan import coverage
from scan_present import correlate


def device(path, depth):
    path.write_text("GRAPHICS_DX12_WAIT generation=1 policy=Wait\nGRAPHICS_MEMORY generation=1 hint=MemoryUsage\n"
                    "GRAPHICS_READY generation=1\nGRAPHICS_SURFACE generation=1 desktop=WindowsDx12Cpu offered=[Mailbox, Fifo]\n"
                    f"GRAPHICS_PRESENT generation=1 desktop=WindowsDx12Cpu mode=Mailbox latency=Some({depth})\n")
    return measured_generation(path, "Mailbox", frame_latency=depth)


def png(path, offset, text=False, caret=None):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    header = struct.pack(">IIBBBBB", 16, 8, 8, 0, 0, 0, 0)
    pixels = (b"\0" + bytes(240 if x == caret else offset + x for x in range(16))) * 8
    label = chunk(b"tEXt", b"Comment\0Identical pixels") if text else b""
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + label + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))
    return {"x": 10, "y": 30, "width": 16, "height": 8, "colors": 16, "sha256": sha(path)}


def inventory_trial(area, index, depth):
    pid, worker = 10 * depth + index, 100 * depth + index
    frequency = 10000
    name = f"rust-{index}"
    ticks = 220 if depth == 1 else 90
    requests = [dict(action="reopen" if i % 2 else "close", hwnd=pid+500, issuedQpc=2000+500*i, responseQpc=2000+500*i+ticks)
                for i in range(20)]
    data = dict(guiPid=pid, inventoryPid=worker, frequency=frequency, requests=requests, firstCompleteQpc=100200, secondCompleteQpc=300200)
    (area / (name + "-scan-requests.json")).write_text(json.dumps(data))
    files = [f"READY {worker} rust", "COUNTS 700000 2100000 0 0 0 0 0 0"]
    for sweep, origin in enumerate((100, 200000)):
        files.extend(f"D {sweep} {i} {origin+i*1000} 1000" for i in range(100))
        files.extend(f"B {sweep} {origin+i*32+1} {origin+i*32+32} 32" for i in range(3125))
    files = "\n".join([*files, "COMPLETE"])
    (area / (name + "-scan-files.log")).write_text(files, encoding="ascii")
    work = coverage(files, requests, data["firstCompleteQpc"], data["secondCompleteQpc"], frequency, worker, "rust")
    events = [f"DXGI {pid} 42 0 0 {q['responseQpc']} {q['responseQpc']+1}" for q in requests[3::2]]
    dxgi = "\n".join(["READY", f"QPC {pid} {frequency}", *events, "COMPLETE"])
    path = area / (name + "-scan-presents.log")
    path.write_text(dxgi, encoding="ascii")
    present = correlate(dxgi, pid, frequency, [1, 310000], work, "Mailbox")
    present.update(decodedEventsSha256=sha(path))
    log = area / (name + "-scan.log")
    scan_device = device(log, depth)
    with log.open("a") as stream:
        stream.write("INVENTORY_COMPLETE files=100000 changed=100000 pass=0\nINVENTORY_COMPLETE files=100000 changed=0 pass=1\n")
    timings = dict.fromkeys(("scan_close_p95_ms", "scan_reopen_p95_ms"), ticks / 10)
    scan = dict(work, guiPid=pid, inventoryPid=worker, allRequests=requests, presentation=present, completedPasses=2,
                unchangedWorker=True, device=scan_device, metrics=timings)
    return dict(device=device(area / (name + ".log"), depth), scan=scan, metrics=dict.fromkeys(METRICS, ticks / 10))


class FrameLatencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.host = {k: k for k in HOST_BUILD}

    def test_paired_limits_preserve_overruns_and_reject_different_runs_depths_and_partial_work(self):
        limits = dict.fromkeys(METRICS, 10)
        inventory = {k: k for k in ("compiledEntry", "approvedBundle", "packages", "sources")}
        for depth, folder in ((1, "measured"), (2, "measured-mailbox-two")):
            area = self.base / folder
            area.mkdir()
            trials = [inventory_trial(area, i, depth) for i in range(1, 4)]
            result = dict(**self.host, referenceBudgetSha256="budget", observerInputs={}, presentMode="Mailbox",
                          desiredMaximumFrameLatency=depth, diagnosticControl=depth == 2,
                          inputs=dict(workload={"files": 100000}, inventory=dict(inventory, gui=self.host["binary"])),
                          trials=trials, comparison=recorder.comparison(limits, recorder.summarize(trials)))
            (area / "result.json").write_text(json.dumps(result))
        pair = paired_frame_latency(self.base, result, limits)
        self.assertEqual(pair["metrics"]["scan_reopen_p95_ms"], {"wpfMaximum": 10, "mailboxOne": 22, "mailboxTwo": 9})
        for key, replacement in (("revision", "other"), ("desiredMaximumFrameLatency", 1), ("presentMode", "Fifo"),
                                 ("trials", trials[1:]), ("diagnosticControl", False), ("referenceBudgetSha256", "other")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                paired_frame_latency(self.base, dict(result, **{key: replacement}), limits)
        missing = deepcopy(result)
        missing["trials"][2]["scan"]["passes"][1]["distinctFiles"] -= 1
        with self.assertRaisesRegex(ValueError, "two-pass"):
            paired_frame_latency(self.base, missing, limits)
        for suffix in ("-requests.json", "-files.log", "-presents.log"):
            path = area / ("rust-1-scan" + suffix)
            saved = path.read_bytes()
            path.unlink()
            with self.subTest(missing=suffix), self.assertRaises(FileNotFoundError):
                paired_frame_latency(self.base, result, limits)
            path.write_bytes((area / ("rust-2-scan" + suffix)).read_bytes())
            with self.subTest(swapped=suffix), self.assertRaises(ValueError):
                paired_frame_latency(self.base, result, limits)
            path.write_bytes(saved)
        trace = area / "rust-3-scan-presents.log"
        saved = trace.read_bytes()
        trace.write_text("Only a marker")
        changed = deepcopy(result)
        changed["trials"][2]["scan"]["presentation"]["decodedEventsSha256"] = sha(trace)
        with self.assertRaisesRegex(ValueError, "DXGI trace"):
            paired_frame_latency(self.base, changed, limits)
        trace.write_bytes(saved)
        device(self.base / "measured-mailbox-two/rust-3-scan.log", 1)
        with self.assertRaisesRegex(ValueError, "frame latency"):
            paired_frame_latency(self.base, result, limits)

    def test_visible_edit_must_use_the_same_pid_hwnd_build_depth_and_changed_original_png(self):
        root = self.base / "observed"
        report = dict(self.host, controls={})
        for depth, name in ((1, "retained-edit"), (2, TWO_FRAME_EDIT)):
            area = root / name
            area.mkdir(parents=True)
            device(area / "subject.log", depth)
            hwnd, pid = 70 + depth, 40 + depth
            generations = ["GRAPHICS_READY generation=1"]
            trial = dict(case="retained-edit", transitions=[dict(hidden=hwnd, reopened=hwnd, generationBefore=generations,
                         generationAfter=generations)], pid=pid, creation100ns=100 + depth, exitCode=0,
                         singleWake=False, subjectLog=sha(area / "subject.log"))
            for phase in ("before", "after"):
                path = area / f"field-{phase}.json"
                field = dict(processId=pid, windowHandle=hwnd, dpi=96, status="passed", onInputDesktop=True, foreground=True, draft="recoverydraft",
                             editedFrame=png(area / (path.name + ".edited.png"), 1 if phase == "after" else 0))
                if phase == "after":
                    field.update(draft="recoverydraftafter", focusBeforeActivation="Dateiname",
                                 difference={"pixels": 128, "columns": 16, "rows": 8, "textChanged": True},
                                 restoredFrame=png(area / (path.name + ".restored.png"), 0))
                path.write_text(json.dumps(field))
                trial[phase + "Field"] = sha(path)
            report["controls"][name] = trial
        output = root / "result.json"
        output.write_text(json.dumps(report))
        edits = visible_edits(self.base, self.host)["controls"]
        self.assertEqual(edits[TWO_FRAME_EDIT]["device"]["desiredMaximumFrameLatency"], 2)
        with self.assertRaisesRegex(ValueError, "different retained"):
            visible_edits(self.base, dict(self.host, binary="other"))
        for key, replacement in (("pid", 41), ("afterField", "stale")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "owned field"):
                mixed = deepcopy(report)
                mixed["controls"][TWO_FRAME_EDIT][key] = replacement
                output.write_text(json.dumps(mixed))
                visible_edits(self.base, self.host)
        output.write_text(json.dumps(report))
        path = root / TWO_FRAME_EDIT / "field-after.json"
        original = json.loads(path.read_bytes())
        for key, change in (("restoredFrame", dict(original["restoredFrame"], x=40)), ("windowHandle", 71),
                            ("difference", {"pixels": 8, "columns": 1, "rows": 8, "textChanged": True}),
                            ("difference", {"pixels": 16, "columns": 2, "rows": 8, "textChanged": True})):
            with self.subTest(key=key, change=change), self.assertRaises(ValueError):
                path.write_text(json.dumps(dict(original, **{key: change})))
                trial["afterField"] = sha(path)
                output.write_text(json.dumps(report))
                visible_edits(self.base, self.host)
        path.write_text(json.dumps(original))
        trial["afterField"] = sha(path)
        output.write_text(json.dumps(report))
        png(root / TWO_FRAME_EDIT / "field-after.json.edited.png", 0)
        with self.assertRaisesRegex(ValueError, "screen pixels"):
            visible_edits(self.base, self.host)
        # The same field raster can have different PNG hashes after a metadata-only change.
        path = root / TWO_FRAME_EDIT / "field-after.json"
        field = json.loads(path.read_bytes())
        field["editedFrame"] = png(path.with_suffix(".json.edited.png"), 0, text=True)
        self.assertNotEqual(field["editedFrame"]["sha256"], field["restoredFrame"]["sha256"])
        field["difference"] = {"pixels": 0, "columns": 0, "rows": 0, "textChanged": False}
        path.write_text(json.dumps(field))
        trial["afterField"] = sha(path)
        output.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "display the changed text"):
            visible_edits(self.base, self.host)

    def test_field_capture_hashes_original_png_bytes_without_optional_powershell_modules(self):
        shell = (Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
                 if os.name == "nt" else shutil.which("pwsh"))
        if not shell:
            self.skipTest("PowerShell is required for the screenshot digest")
        path = self.base / "field [edited].png"
        encoded = self.base / "same pixels.png"
        expected = [png(path, 0)["sha256"], png(encoded, 0, text=True)["sha256"]]
        self.assertNotEqual(*expected)
        driver = """
$ErrorActionPreference = 'Stop'
$PSModuleAutoLoadingPreference = 'None'
if (Get-Module Microsoft.PowerShell.Utility) { Remove-Module Microsoft.PowerShell.Utility -Force }
if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) { throw 'Expected the isolated host to lack Get-FileHash.' }
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($env:IFW_PIXEL_SOURCE, [ref]$null, [ref]$errors)
if ($errors.Count) { throw $errors[0] }
$hash = $ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Get-FieldPngHash'}, $true)
$capture = $ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Capture-SubjectField'}, $true)
$calls = @($capture.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst] -and $n.GetCommandName() -ceq 'Get-FieldPngHash'}, $true))
if ($calls.Count -ne 1 -or $calls[0].CommandElements[1].Extent.Text -cne '$png') { throw 'Expected the capture to hash its saved PNG.' }
. ([scriptblock]::Create($hash.Extent.Text))
Get-FieldPngHash $env:IFW_PIXEL_FILE
$lock = [IO.File]::Open($env:IFW_PIXEL_FILE, 'Open', 'ReadWrite', 'None')
try {
    try { Get-FieldPngHash $env:IFW_PIXEL_FILE; throw 'Reported a digest for a locked capture.' } catch [IO.IOException] {}
} finally { $lock.Dispose() }
try { Get-FieldPngHash ($env:IFW_PIXEL_FILE + '.missing'); throw 'Reported a digest for a missing capture.' } catch [IO.FileNotFoundException] {}
Get-FieldPngHash $env:IFW_PIXEL_ENCODED
"""
        env = dict(os.environ, IFW_PIXEL_SOURCE=str(QA / "observe-windows-input.ps1"),
                   IFW_PIXEL_FILE=str(path), IFW_PIXEL_ENCODED=str(encoded), PSModulePath=str(self.base),
                   POWERSHELL_TELEMETRY_OPTOUT="1")
        if os.name != "nt":
            for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
                env[key] = str(self.base / key)
        proc = subprocess.run([shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", driver],
                              cwd=self.base, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), expected)

    @unittest.skipUnless(os.name == "nt", "requires the Windows System.Drawing bitmap decoder")
    def test_native_bitmap_comparison_rejects_equal_pixels_and_a_blinking_or_moved_caret(self):
        path = self.base
        for name, options in (("base", {}), ("encoded", {"text": True}), ("blink", {"caret": 2}), ("moved", {"caret": 13})):
            png(path / (name + ".png"), 0, **options)
        png(path / "text.png", 1)
        driver = """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($env:IFW_PIXEL_SOURCE, [ref]$null, [ref]$errors)
$definitions = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Get-FieldPixelDifference'}, $true))
if ($errors -or $definitions.Count -ne 1) { throw 'Expected the shared bitmap comparison.' }
. ([scriptblock]::Create($definitions[0].Extent.Text))
$bounds = @{x=10; y=30; width=16; height=8}
$results = foreach ($pair in @('base,encoded','base,blink','blink,moved','base,text')) {
    $left, $right = $pair.Split(',')
    Get-FieldPixelDifference (Join-Path $env:IFW_PIXEL_DIR "$left.png") (Join-Path $env:IFW_PIXEL_DIR "$right.png") $bounds $bounds 96
}
ConvertTo-Json -InputObject @($results) -Compress
"""
        env = dict(os.environ, IFW_PIXEL_DIR=str(path), IFW_PIXEL_SOURCE=str(QA / "observe-windows-input.ps1"))
        shell, attempts = recorder.load_windows_fixture().select_powershell(path, "accessibility", env)
        self.assertTrue(shell, attempts)
        proc = subprocess.run([shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Sta", "-Command", driver],
                              cwd=path, env=env, capture_output=True, text=True, check=True, timeout=30)
        got = json.loads(proc.stdout)
        self.assertEqual([(r["pixels"], r["columns"], r["rows"], r["textChanged"]) for r in got],
                         [(0, 0, 0, False), (8, 1, 8, False), (16, 2, 8, False), (128, 16, 8, True)])
