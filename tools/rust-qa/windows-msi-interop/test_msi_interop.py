from copy import deepcopy
import ctypes as c
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from common import AFTER, BEFORE, HERE, QA, launcher, module, sha
from msi_evidence import activation, sparse_inventory, verify_transactions


def kernel_rows():
    lines = ["READY 41 rust", "COUNTS 8 10 0 0 0 0 0 0"]
    for sweep in range(2):
        for i in range(100):
            enum = 400 + 150 * sweep if i == 0 else 0
            lines.append(f"D {sweep} {i} {enum} {int(i == 0)}")
        at = 420 + 150 * sweep
        lines.append(f"B {sweep} {at} {at} 1")
    return "\n".join(lines + ["COMPLETE"])


def sample():
    root = dict(hwnd=55, pid=40, tid=20, title="Desktop input probe", desktop="Default")
    show = dict(event="show", hwnd=55, root=True, winEventTimeMs=24)
    hide = dict(event="hide", hwnd=55, root=True, winEventTimeMs=20)
    events = [hide, show]
    members = [dict(role="primary", pid=40, parent=10, creation100ns=500, image="native-gui-assessment.exe"),
               dict(role="worker", pid=41, parent=40, creation100ns=520, image="ifw-performance-worker.exe")]
    row = dict(status="observed", primary=[40,500], worker=[41,520], frequency=1000, jobDrained=True,
               quit=dict(method="control-Q",exitCode=0), cleanupConfirmed=True, stagedDirectory=dict(removed=True),
               stagedImageCleanup={"gui":dict(absent=True)}, before=dict(members=members,pids=[40,41]),
               after=dict(members=deepcopy(members),pids=[40,41]), secondary=dict(pid=50,created=599,exit=0,activeAfter=0,
               totalProcesses=1,arguments=[],sha256="c"*64,releasedAfterQpc=200), reopenedByQpc=250,
               root=dict(first={**root,"showEvent":dict(show,winEventTimeMs=12)}, hidden={**root,"hideEvent":hide},
                         reopened={**root,"events":events}, afterInventory={**root,"events":events},
                         msiShow=dict(showEvent=show,earliestMs=21,releasedByMs=22,observedMs=25,showMs=24,distinctTicks=True),
                         lifetimeBeforeQuit=[[55,"create",10]]),
               challenge=dict(introducedAfterQpc=300,observedByQpc=600,etlBytes=64,etlSha256="a"*64,sha256="b"*64,traceExit=0))
    log = "\n".join(["LAUNCHER_PRIMARY pid=40", "INVENTORY_WORKER pid=41", "INVENTORY_COMPLETE files=0 changed=0 pass=0",
                     "INVENTORY_COMPLETE files=0 changed=0 pass=1", "WINDOW_HIDDEN", "LAUNCHER_OPEN client=50",
                     "INVENTORY_COMPLETE files=1 changed=1 pass=2", "INVENTORY_COMPLETE files=1 changed=0 pass=3", "DRAINED passes=7"])
    return row, log, kernel_rows()


class MsiInteropTests(unittest.TestCase):
    def test_suspended_member_check_uses_the_real_native_pid_list_decoder(self):
        observer = module("ifw_msi_local_control", HERE / "observe.py")
        api = object.__new__(launcher().recorder.Win32)
        members = [50]
        def query(job, info, buf, size, result):
            self.assertEqual((job, info), (12, 3))
            counts = (c.c_uint32 * 2).from_buffer(buf)
            counts[:] = (len(members), len(members))
            (c.c_size_t * len(members)).from_buffer(buf, 8)[:] = members
            result._obj.value = 8 + c.sizeof(c.c_size_t) * len(members)
            return True
        api.query_job = query
        second = SimpleNamespace(pid=50, benchmark_job=12, poll=lambda: None)
        observer.verify_suspended_secondary(api, second)
        for members in ([], [51], [50, 51]):
            with self.assertRaises(ValueError):
                observer.verify_suspended_secondary(api, second)

    def test_transaction_replay_requires_original_hashes_both_logs_and_order(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            records = {}
            for name in ("install.log", "uninstall.log"):
                (base / name).write_bytes(name.encode("utf-16"))
                records[name] = dict(sha256=sha(base / name), nativePath="D:\\capture\\" + name)
            first = dict(operation="/i", log="install.log", subject=r"D:\work\immich-folder-watch-3.0.4-win-x64.msi",
                         timedOut=False, exitCode=0)
            second = dict(operation="/x", log="uninstall.log", subject="product", timedOut=False, exitCode=0)
            identity = dict(productCode="product")
            for ops in ([second, first], [first, first]):
                with self.assertRaisesRegex(ValueError, "followed"):
                    verify_transactions(base, records, ops, identity, "windows-x64")
            left, right = (base / "install.log", base / "uninstall.log")
            left.write_bytes(right.read_bytes())
            with self.assertRaisesRegex(ValueError, "unbound"):
                verify_transactions(base, records, [first, second], identity, "windows-x64")
            left.write_bytes("install.log".encode("utf-16"))
            right.unlink()
            with self.assertRaisesRegex(ValueError, "unbound"):
                verify_transactions(base, records, [first, second], identity, "windows-x64")

    def test_each_cli_resolves_the_existing_inventory_builder_in_a_fresh_interpreter(self):
        code = """
import runpy, sys
from pathlib import Path
base = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(base))
namespace = runpy.run_path(str(base / sys.argv[2]), run_name='ifw_cli_test')
from common import launcher
from msi_evidence import verify
native = launcher()
assert Path(sys.modules[native.recorder.build_subject.__module__].__file__).resolve() == base.parent / 'windows-inventory/subject.py'
assert Path(sys.modules[verify.__module__].__file__).resolve() == base / 'msi_evidence.py'
"""
        for script in ("run.py","observe.py","readback.py"):
            subprocess.run([sys.executable, "-B", "-c", code, str(HERE), script], cwd=HERE, check=True)

    def test_reviewed_patch_changes_only_the_private_launcher(self):
        original = QA / "gui/src/windows_launcher.rs"
        self.assertEqual(sha(original), BEFORE)
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "src").mkdir()
            changed = base / "src/windows_launcher.rs"
            shutil.copyfile(original,changed)
            subprocess.run(["git","-c","core.autocrlf=false","apply","--no-index","--whitespace=error","-"],
                           cwd=base,input=(HERE / "launcher.patch").read_bytes(),check=True)
            self.assertEqual(sha(changed), AFTER)
            source = changed.read_text(encoding="utf-8")
            self.assertLess(source.index("if msi_primary {",source.index("if !primary {")),source.index("local::connect(&pipe"))
            self.assertIn("let client = local::peer_pid(&pipe, false)?;",source)
        self.assertEqual(sha(original), BEFORE)

    def test_two_post_reopen_file_queries_and_worker_are_bound_to_the_original(self):
        row, log, trace = sample()
        result = activation(row, log, trace, "c"*64)
        self.assertEqual(result["kernelFileQueries"], [dict(directoryQpc=400,fileQpc=420),dict(directoryQpc=550,fileQpc=570)])
        for fake in (trace.replace("READY 41", "READY 42"), trace.replace("1 570 570 1","1 300 300 1"),
                     trace.replace("D 1 0 550 1","D 1 0 550 0"),trace.replace("0 0 0 0 0 0","0 0 0 0 1 0"),
                     trace.replace("D 0 1 0 0","D 0 1 399 1"),trace.replace("B 0 420 420 1\n","")):
            with self.assertRaises(ValueError):
                sparse_inventory(fake,41,300,600)

    def test_success_exit_alone_recreated_window_and_replaced_worker_cannot_pass(self):
        row,log,trace = sample()
        for field,value in (("pid",51),("activeAfter",1),("exit",2),("totalProcesses",2),("arguments",["--autostart"])):
            with self.assertRaises(ValueError):
                activation(dict(row,secondary={**row["secondary"],field:value}),log,trace,"c"*64)
        for name in ("hidden","reopened","afterInventory"):
            edit = deepcopy(row)
            edit["root"][name]["hwnd"] = 66
            with self.assertRaises(ValueError):
                activation(edit,log,trace,"c"*64)
        edit = deepcopy(row)
        edit["after"]["members"][1]["creation100ns"] += 1
        with self.assertRaises(ValueError):
            activation(edit,log,trace,"c"*64)
        for fake in (log.replace("LAUNCHER_OPEN client=50","LAUNCHER_OPEN client=25"),
                     log.replace("files=1 changed=1","files=0 changed=0"),log.replace("files=1 changed=0","files=1 changed=1")):
            with self.assertRaises(ValueError):
                activation(row,fake,trace,"c"*64)

    def test_same_uptime_tick_or_file_query_before_reopen_cannot_establish_order(self):
        row,log,trace=sample()
        row["root"]["msiShow"]["releasedByMs"] = 24
        with self.assertRaises(ValueError):
            activation(row,log,trace,"c"*64)
        row,log,trace=sample()
        row["reopenedByQpc"] = 401
        with self.assertRaises(ValueError):
            activation(row,log,trace,"c"*64)

    def test_independent_x64_trace_requires_zero_loss_from_attach_to_etl_decode(self):
        row, log, trace = sample()
        ready, ledger = trace.split("\n", 1)
        def phase(name, at):
            return f"MSI_ETW {name} pid=41 qpc={at} mode=134217729 eventsLost=0 logLost=0 realtimeLost=0 allocated=128 written=32"
        snapshots = [phase("attached",290), ready, phase("captured",610), "MSI_DISABLE 0",
                     phase("disabled",620), phase("stopped",630), "MSI_DECODE 0 0 0"]
        original = "\n".join([*snapshots, ledger])
        def check(text):
            return activation(row, log, text, "c"*64, independent=True)
        result = check(original)
        self.assertEqual(result["fileTracePhases"]["captured"]["qpc"], 610)
        self.assertEqual([x["fileQpc"] for x in result["kernelFileQueries"]], [420, 570])
        for index in (0, 2, 4, 5):
            for old, new in (("eventsLost=0","eventsLost=134"), ("logLost=0","logLost=1"),
                             ("realtimeLost=0","realtimeLost=1"), ("mode=134217729","mode=1"), ("pid=41","pid=42")):
                damaged = [*snapshots]
                damaged[index] = damaged[index].replace(old,new)
                with self.subTest(index=index, field=old), self.assertRaises(ValueError):
                    check("\n".join([*damaged,ledger]))
        for changed in (trace, original.replace("MSI_DECODE 0 0 0","MSI_DECODE 0 1273 0"),
                        original.replace("MSI_DECODE 0 0 0","MSI_DECODE 0 0 1"),
                        original.replace("MSI_DISABLE 0","MSI_DISABLE 1460"), original.replace("qpc=610","qpc=599"),
                        original.replace("B 1 570 570 1", "B 1 0 0 0")):
            with self.assertRaises(ValueError):
                check(changed)
        row["challenge"]["traceExit"] = 4
        with self.assertRaises(ValueError):
            check(original)

    def test_file_trace_selects_its_mode_and_records_a_failed_decoder_exit(self):
        from observe import file_trace
        for independent, code in ((False,0), (True,0), (True,4)):
            with self.subTest(independent=independent, exit=code), tempfile.TemporaryDirectory() as tmp:
                trial = Path(tmp)
                out = trial / "evidence"
                out.mkdir()
                helper = trial / "file-observer.exe"
                record = {}
                child = SimpleNamespace(returncode=None, poll=lambda: None)
                def start(args, **kwargs):
                    self.assertEqual(args[:2], [helper,"41"])
                    self.assertEqual(args[3:], [trial / "files.etl",trial / "empty","msi-rust" if independent else "rust"])
                    kwargs["stdout"].write(b"READY 41 rust\n")
                    return child
                def finish(process, observer, area, etl, name, timeout):
                    self.assertIs(process,child)
                    self.assertEqual((observer,area,timeout), (helper,trial,45))
                    self.assertTrue(name.startswith("IFW-Files-"))
                    etl.write_bytes(b"owned test ETL")
                    process.returncode = code
                recorder = SimpleNamespace(await_value=lambda test, *_, **kw: self.assertTrue(test()),
                                           finish_owned_trace=finish)
                with patch("observe.subprocess.Popen", side_effect=start):
                    def capture():
                        with file_trace(recorder, helper, trial, out, 41, record, independent=independent):
                            pass
                    if code:
                        with self.assertRaisesRegex(ValueError, "decoder exit 4"):
                            capture()
                    else:
                        capture()
                self.assertEqual(record["traceExit"], code)
                self.assertEqual(record["etlBytes"], len(b"owned test ETL"))
                self.assertEqual((trial / "files.etl").exists(), bool(code))
                if code:
                    self.assertEqual(record["etlSha256"], sha(trial / "files.etl"))
