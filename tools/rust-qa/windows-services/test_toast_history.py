"""Regression controls for inbox notification history, selective removal and archived readback."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import json
import os
from pathlib import Path, PureWindowsPath
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, call, patch
from uuid import UUID

import toast_history as h
import toast_display_name as registration

TOKEN = "1234567890ab4def9123456789abcdef"
TARGET = "x86_64-pc-windows-msvc"
DESKTOP = dict(windowStation="WinSta0", stationVisible=True, threadDesktop="Default", threadReceivesInput=True,
               inputDesktop="Default", inputObjectReceivesInput=True, session=2, activeConsoleSession=2,
               wts=dict(session=2, connectionState=0, lockFlags=1))
IMPORTS = {"api-ms-win-core-winrt-l1-1-0.dll": ["RoInitialize", "RoUninitialize"],
           "propsys.dll": ["InitPropVariantFromCLSID", "PropVariantChangeType"],
           "shell32.dll": ["SetCurrentProcessExplicitAppUserModelID"], "advapi32.dll": ["GetTokenInformation"],
           "kernel32.dll": ["GetLastError"]}


def item(operation, state, flags):
    fields = dict(operation=operation, aumid="IFW.RustQA.Toast." + TOKEN, elevated="true", session="2",
                  installedLinkVerified="true")
    phases = ["identity", "shortcut"]
    if operation == "prepare":
        del fields["installedLinkVerified"]
        fields["prepared"] = "true"
    elif operation == "register":
        fields["shellNotified"] = "true"
    elif operation == "inspect":
        phases.append("history")
        fields["count"] = str(len(state))
        for mode in state:
            fields.update({mode + "." + k: v for k, v in dict(tag=mode[0] + TOKEN[:15], group="g" + TOKEN[16:31],
                          title=f"IFW synthetic {mode} {TOKEN}", body=f"Rust {mode} notification history {TOKEN}").items()})
    else:
        command, mode = operation.split("-")
        if command == "post":
            phases.append("notifier")
            fields["setting"] = flags.get("setting", "0")
            if fields["setting"] == "0":
                phases.extend(["content", "show"])
                fields.update(showReturned="true", suppressPopup=str(mode == "quiet").lower(),
                              expirationTicks="135210401234560000", mirroringDisabled="true")
                if not flags.get("silentDrop"):
                    state.add(mode)
        elif command == "remove":
            phases.append("remove")
            fields["removeReturned"] = "true"
            if flags.get("broadRemoval"):
                state.clear()
            elif not flags.get("ignoreRemoval"):
                state.discard(mode)
    return dict(fields=fields, phases=phases, hresult=None)


def trial(flags=None, directory=None):
    state, steps, flags = set(), [], flags or {}
    report = dict(token=TOKEN, target=TARGET, desktop=deepcopy(DESKTOP), processes=steps)
    tick = [0]

    def call(operation):
        record = item(operation, state, flags)
        index = len(steps)
        pid = 1400 + index
        record["fields"]["pid"] = str(pid)
        name = f"{index:03}-{operation}.txt"
        proc = dict(operation=operation, pid=pid, exit=0, jobEmpty=True, machine=(0x8664, 0x8664),
                    creation100ns=index + 40, log=name)
        steps.append(proc)
        if directory:
            raw = "".join("phase=" + stage + "\n" for stage in record["phases"])
            raw += "".join(k + "=" + v + "\n" for k, v in record["fields"].items())
            (directory / name).write_bytes(raw.encode())
            proc["logSha256"] = h.sha(directory / name)
        return record

    def advance(_):
        tick[0] += 10

    if directory:
        call("prepare")
        call("register")
        (directory / "shortcut.bin").write_bytes(b"synthetic unit control")
        h.write(directory / "desktop.json", report["desktop"])
        h.write(directory / "pe-imports.json", IMPORTS)
        build = dict(hosted=True, target=TARGET, head="1"*40, workflowRun="123", workflowAttempt="1",
                     checkoutVerified=True, sourceFiles={"fixture.rs": "8"*64}, canonicalGraphSha256="7"*64,
                     steps=dict.fromkeys(("compiler", "inventory", "clippy", "build", "toast-controls"), 0),
                     probeSha256="2"*64, evidenceFiles={"pe-imports.json": h.sha(directory / "pe-imports.json")})
        h.write(directory / "native-build.json", build)
        report.update(profileRemoved=True, ownedFolderCreated=True, ownedFolderRemoved=True,
                      run=build["workflowRun"], attempt=build["workflowAttempt"], head=build["head"],
                      binarySha256=build["probeSha256"], graphSha256=build["canonicalGraphSha256"],
                      observerInputs=build["sourceFiles"], earlyResultSha256=h.sha(directory / "native-build.json"),
                      shortcut=dict(knownFolder=h.PROGRAMS, relative=f"ifw-shell-{TOKEN}/{h.LINK}",
                                    sha256=h.sha(directory / "shortcut.bin")))

    def run():
        status = h.exchange(call, TOKEN, report, delay=advance, clock=lambda: tick[0])
        if directory:
            report["evidenceFiles"] = h.evidence_files(directory)
        return status

    return run, report


class ToastHistoryTests(unittest.TestCase):
    def test_compare_display_name_only_for_two_absent_settings_before_show(self):
        for phase, code, should_register in (("notifier-setting", h.NOT_FOUND, True),
                                            ("notifier-create", h.NOT_FOUND, False),
                                            ("notifier-setting", -2147024891, False)):
            with self.subTest(phase=phase, code=code):
                state, report, windows, operations = set(), {}, [], []

                @contextmanager
                def register():
                    windows.append("installed")
                    try:
                        yield
                    finally:
                        windows.append("removed")

                def call(op):
                    operations.append(op)
                    if op.startswith("post-") and not windows:
                        return dict(fields={}, phases=["identity", "shortcut", phase], hresult=code)
                    return item(op, state, {})

                if should_register:
                    self.assertEqual(h.assess_registration(call, TOKEN, report, register), "passed")
                    self.assertEqual(windows, ["installed", "removed"])
                    self.assertTrue(report["shortcutOnly"]["finallyEmpty"])
                    self.assertEqual(operations[:4], ["inspect", "post-quiet", "post-normal", "inspect"])
                    self.assertEqual(report["cleanup"], {"normal": ["quiet"], "quiet": []})
                else:
                    with self.assertRaises(h.Unavailable):
                        h.assess_registration(call, TOKEN, report, register)
                    self.assertEqual(windows, [])
                    self.assertTrue(report["finallyEmpty"])

    def test_only_new_registry_handles_are_cleaned_up_after_a_sender_failure(self):
        api = Mock()
        api.reg.KEY_READ, api.reg.KEY_SET_VALUE = 1, 2
        api.create.return_value = (1001, 2)
        record = {}
        with self.assertRaisesRegex(ValueError, "already exists"):
            with registration.new_identity(api, 1000, "test-identity", record):
                self.fail("The existing identity must remain untouched")
        api.delete_empty.assert_not_called()
        api.reg.CloseKey.assert_called_once_with(1001)
        self.assertEqual(record["leafDisposition"], 2)
        api.create.return_value = (1002, 1)
        with self.assertRaisesRegex(RuntimeError, "sender"):
            with registration.new_identity(api, 1000, "test-identity", record):
                raise RuntimeError("sender")
        api.delete_empty.assert_called_once_with(1002)
        api.reg.CloseKey.assert_called_with(1002)

    def test_registry_parent_is_only_opened_and_cleanup_uses_the_original_leaf(self):
        api = Mock()
        reg = api.reg
        reg.HKEY_CURRENT_USER, reg.KEY_READ, reg.KEY_CREATE_SUB_KEY, reg.KEY_SET_VALUE, reg.REG_SZ = 99, 1, 4, 2, 1
        aumid = registration.identity(TOKEN)
        reg.OpenKey.side_effect = [nullcontext(71), nullcontext(73), FileNotFoundError()]
        api.create.return_value = (72, 1)
        reg.QueryInfoKey.return_value = (0, 1, 0)
        reg.QueryValueEx.return_value = (h.DISPLAY + TOKEN, reg.REG_SZ)
        receipt = {}
        with registration.display_name(TOKEN, receipt, api=api):
            self.assertTrue(receipt["readback"])
        self.assertEqual(reg.OpenKey.call_args_list, [
            call(99, h.PARENT, 0, reg.KEY_READ | reg.KEY_CREATE_SUB_KEY),
            call(71, aumid, 0, reg.KEY_READ), call(71, aumid, 0, reg.KEY_READ)])
        api.create.assert_called_once_with(71, aumid, reg.KEY_READ | reg.KEY_SET_VALUE | registration.DELETE)
        api.delete_empty.assert_called_once_with(72)
        reg.DeleteValue.assert_called_once_with(72, "DisplayName")
        self.assertTrue(receipt["leafRemoved"])
        self.assertEqual(receipt["namespaceAcquisition"], "opened")

    def test_collision_precheck_and_missing_classes_hive_make_no_registry_changes(self):
        api = Mock()
        reg = api.reg
        reg.HKEY_CURRENT_USER, reg.KEY_READ, reg.KEY_CREATE_SUB_KEY = 99, 1, 4
        reg.OpenKey.side_effect = [nullcontext(70), FileNotFoundError(), FileNotFoundError(), FileNotFoundError()]
        self.assertFalse(registration.identity_absent(TOKEN, reg))
        self.assertTrue(registration.identity_absent(TOKEN, reg))
        receipt = {}
        with self.assertRaisesRegex(registration.MissingNamespace, "is absent"):
            with registration.display_name(TOKEN, receipt, api=api):
                self.fail("An unavailable Classes hive must not start the registered exchange")
        self.assertEqual(receipt["parent"], h.PARENT)
        self.assertFalse(receipt["parentOpened"])
        self.assertNotIn("leafDisposition", receipt)
        self.assertEqual(reg.OpenKey.call_args_list, [
            call(99, h.PARENT + "\\" + registration.identity(TOKEN), 0, reg.KEY_READ)] * 2 +
            [call(99, h.PARENT, 0, reg.KEY_READ | reg.KEY_CREATE_SUB_KEY),
             call(99, registration.CLASSES, 0, reg.KEY_CREATE_SUB_KEY)])
        api.create.assert_not_called()
        api.delete_empty.assert_not_called()
        reg.SetValueEx.assert_not_called()

    def test_fresh_user_creates_only_the_namespace_and_owns_only_the_test_leaf(self):
        for disposition, acquisition in ((1, "created"), (2, "opened-concurrently")):
            with self.subTest(acquisition=acquisition):
                api = Mock()
                reg = api.reg
                reg.HKEY_CURRENT_USER, reg.KEY_READ, reg.KEY_CREATE_SUB_KEY, reg.KEY_SET_VALUE, reg.REG_SZ = 99, 1, 4, 2, 1
                reg.OpenKey.side_effect = [FileNotFoundError(), nullcontext(70), nullcontext(73), FileNotFoundError()]
                api.create.side_effect = [(71, disposition), (72, 1)]
                reg.QueryInfoKey.return_value = (0, 1, 0)
                reg.QueryValueEx.return_value = (h.DISPLAY + TOKEN, reg.REG_SZ)
                receipt = {}
                with self.assertRaisesRegex(RuntimeError, "sender"):
                    with registration.display_name(TOKEN, receipt, api=api):
                        raise RuntimeError("sender failed")
                self.assertEqual(receipt["namespaceAcquisition"], acquisition)
                self.assertTrue(receipt["leafRemoved"])
                self.assertEqual(api.create.call_args_list, [
                    call(70, registration.NAMESPACE, reg.KEY_READ | reg.KEY_CREATE_SUB_KEY, volatile=False),
                    call(71, registration.identity(TOKEN), reg.KEY_READ | reg.KEY_SET_VALUE | registration.DELETE)])
                api.delete_empty.assert_called_once_with(72)
                reg.SetValueEx.assert_called_once_with(72, "DisplayName", 0, reg.REG_SZ, h.DISPLAY + TOKEN)
                reg.DeleteValue.assert_called_once_with(72, "DisplayName")
                self.assertEqual(reg.CloseKey.call_args_list, [call(72), call(71)])

    def test_replay_requires_the_original_shortcut_only_processes_and_registry_cleanup(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            run, report = trial(directory=directory)
            run()
            build_path = directory / "native-build.json"
            build = json.loads(build_path.read_bytes())
            build["sourceFiles"][h.DISPLAY_NAME_SOURCE] = "b"*64
            h.write(build_path, build)
            report.update(observerInputs=build["sourceFiles"], earlyResultSha256=h.sha(build_path), registryIdentityInitiallyAbsent=True)
            procs = report["processes"]
            for i in reversed(range(2, len(procs))):
                proc = procs[i]
                new = f"{i + 4:03}-{proc['operation']}.txt"
                (directory / proc["log"]).rename(directory / new)
                proc["log"] = new
            first = []
            for index, op in enumerate(("inspect", "post-quiet", "post-normal", "inspect"), 2):
                pid, name = 5000 + index, f"{index:03}-{op}.txt"
                log = (f"operation={op}\naumid=IFW.RustQA.Toast.{TOKEN}\nphase=identity\npid={pid}\n"
                       "session=2\nelevated=true\nphase=shortcut\ninstalledLinkVerified=true\n")
                refused = op.startswith("post-")
                if refused:
                    log += ("phase=notifier-create\nready.1.create=0\nphase=notifier-setting\n"
                            f"ready.1.setting={h.NOT_FOUND}\nProbe HRESULT {h.NOT_FOUND}\n")
                else:
                    log += "phase=history\ncount=0\n"
                (directory / name).write_bytes(log.encode())
                proc = dict(operation=op, pid=pid, exit=int(refused), jobEmpty=True, machine=[0x8664, 0x8664],
                            creation100ns=50000 + index, log=name, logSha256=h.sha(directory / name))
                if refused:
                    proc["notifierReadiness"] = [{"create": 0, "setting": h.NOT_FOUND}]
                first.append(proc)
            procs[2:2] = first
            report["shortcutOnly"] = dict(initiallyEmpty=True, finallyEmpty=True, cleanup={},
                                          modes={m: {"platformError": f"post-{m} returned HRESULT 0x80070490 during notifier-setting"}
                                                 for m in ("quiet", "normal")})
            receipt = dict(startProcess=6, endProcess=len(procs), aumid="IFW.RustQA.Toast." + TOKEN,
                           displayName=h.DISPLAY + TOKEN, view="native", leafDisposition=1,
                           parent=h.PARENT, parentOpened=True, namespaceAcquisition="created", readback=True, leafRemoved=True)
            path = directory / "display-name.json"
            for override in ({}, {"startProcess": 5}, {"endProcess": 7}, {"leafDisposition": 2},
                             {"leafRemoved": False}, {"parentOpened": False}, {"parent": "other"}, {"namespaceAcquisition": None}):
                h.write(path, {**receipt, **override})
                report["evidenceFiles"] = h.evidence_files(directory)
                if not override:
                    self.assertTrue(h.replay(directory, report)["finallyEmpty"])
                else:
                    with self.subTest(override=override), self.assertRaisesRegex(ValueError, "registration"):
                        h.replay(directory, report)
            del receipt["namespaceAcquisition"]
            build["sourceFiles"][h.DISPLAY_NAME_SOURCE] = h.OPEN_ONLY_SOURCE_SHA256
            h.write(build_path, build)
            h.write(path, receipt)
            report.update(observerInputs=build["sourceFiles"], earlyResultSha256=h.sha(build_path),
                          evidenceFiles=h.evidence_files(directory))
            self.assertTrue(h.replay(directory, report)["finallyEmpty"])
            report["registryIdentityInitiallyAbsent"] = False
            with self.assertRaisesRegex(ValueError, "collision check"):
                h.replay(directory, report)

    def test_prepare_uses_its_own_profile_marker_and_the_original_default_desktop_launcher(self):
        for arch, (target, machine) in h.TARGET.items():
            with self.subTest(target=target):
                self.check_prepare_launch(arch, target, machine)

    def check_prepare_launch(self, arch, target, machine):
        import notification_probe as probe
        import named_process
        import build

        class ReachedNativeLaunch(Exception):
            """The unmodified launcher's checks completed before constructing the Win32 kernel wrapper."""

        root = PureWindowsPath(r"C:\fixture\runner-temp")
        area = root / ("ifw-shell-" + TOKEN)
        exe = root.parent / "ifw-windows-services-probe.exe"
        parent = dict(RUNNER_TEMP=str(root), RUNNER_ARCH=arch, USERPROFILE=r"C:\Users\runneradmin",
                      APPDATA=r"C:\Users\runneradmin\AppData\Roaming", LOCALAPPDATA=r"C:\Users\runneradmin\AppData\Local",
                      TEMP=r"C:\old-temp", TMP=r"C:\old-tmp", IFW_QA_INVENTORY_TOKEN="f"*32,
                      IFW_QA_ISOLATED="0", IFW_QA_TOAST_HISTORY="0")
        api = Mock()
        api.wait_job_empty.return_value = True
        api.close.return_value = True
        record = {}
        with (TemporaryDirectory() as temporary, patch.dict(os.environ, parent, clear=True),
              patch.object(h.uuid, "uuid4", return_value=UUID(hex=TOKEN)), patch.object(probe, "Win32", return_value=api),
              patch.object(probe, "Desktop", return_value=Mock(context=Mock(return_value=DESKTOP))),
              patch.object(build, "pe_machine", return_value=machine),
              patch.object(h, "identity_absent", side_effect=[False, True]) as absent,
              patch.object(probe, "pin_path", return_value=nullcontext()) as image_pin,
              patch.object(probe, "fixture_profile", return_value=nullcontext(area)) as profile,
              patch.object(probe, "pin_new_marker") as marker, patch.dict(sys.modules, msvcrt=Mock()),
              patch.object(probe, "start", wraps=named_process.start) as start,
              patch.object(named_process, "Kernel", side_effect=ReachedNativeLaunch) as kernel):
            collision = {}
            with self.assertRaisesRegex(ValueError, "identity already exists"):
                h.measure(target, exe, Path(temporary), collision)
            self.assertFalse(collision["registryIdentityInitiallyAbsent"])
            start.assert_not_called()
            with self.assertRaises(ReachedNativeLaunch):
                h.measure(target, exe, Path(temporary), record)
        self.assertEqual(absent.call_args_list, [call(TOKEN), call(TOKEN)])
        profile.assert_called_once_with(api, Path(str(root)), TOKEN, record)
        image_pin.assert_called_once_with(api, exe, False)
        self.assertEqual(marker.call_args.args[1:], (api, area / "synthetic.fixture", TOKEN))
        kernel.assert_called_once()
        start.assert_called_once()
        self.assertEqual(start.call_args.args, (exe, ["--hosted-toast-history", str(area), TOKEN, "prepare"]))
        launch = start.call_args.kwargs
        self.assertEqual((launch["desktop"], launch["cwd"], launch["primary"]), ("Default", area, True))
        self.assertEqual(launch["env"], {**parent, "TEMP": str(area), "TMP": str(area), "IFW_QA_TOAST_HISTORY": "1",
                                        "IFW_QA_INVENTORY_TOKEN": TOKEN, "IFW_QA_ISOLATED": "1"})

    def test_pre_fix_environment_and_foreign_desktop_are_refused_before_any_native_launch(self):
        import notification_probe
        import named_process

        old = {"IFW_QA_TOAST_HISTORY": "1"}
        valid = {**old, "IFW_QA_INVENTORY_TOKEN": TOKEN, "IFW_QA_ISOLATED": "1"}
        with patch.dict(sys.modules, msvcrt=Mock()), patch.object(named_process, "Kernel") as kernel:
            for env, desktop in ((old, "Default"), ({**valid, "IFW_QA_ISOLATED": "0"}, "Default"),
                                 ({**valid, "IFW_QA_INVENTORY_TOKEN": "invalid"}, "Default"), (valid, "Winlogon")):
                with self.subTest(env=env, desktop=desktop), self.assertRaisesRegex(ValueError, "verified fixture desktop"):
                    notification_probe.start(r"C:\fixture\probe.exe", [], cwd=r"C:\fixture", env=env, stream=None,
                                             desktop=desktop, primary=True)
            kernel.assert_not_called()

    def test_independent_rows_and_selective_removal_replay(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            run, report = trial(directory=directory)
            self.assertEqual(run(), "passed")
            self.assertEqual(h.replay(directory, report)["cleanup"], {"normal": ["quiet"], "quiet": []})
            altered = deepcopy(report)
            altered["modes"]["normal"]["observed"] = []
            with self.assertRaisesRegex(ValueError, "differs from the reported outcome"):
                h.replay(directory, altered)
            observation = next(p for p in report["processes"] if p["operation"] == "inspect"
                               and b"normal.title" in (directory / p["log"]).read_bytes())
            raw = directory / observation["log"]
            raw.write_bytes(raw.read_bytes().replace(b"normal.title=IFW", b"normal.title=WRONG"))
            observation["logSha256"] = h.sha(raw)
            report["evidenceFiles"] = h.evidence_files(directory)
            with self.assertRaisesRegex((ValueError, RuntimeError), "History content|exact toast cleanup"):
                h.replay(directory, report)

    def test_missing_or_truncated_import_table_rejected_after_reindexing(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            run, report = trial(directory=directory)
            run()
            table = directory / "pe-imports.json"
            table.unlink()
            report["evidenceFiles"] = h.evidence_files(directory)
            with self.assertRaisesRegex(ValueError, "raw native evidence"):
                h.replay(directory, report)
            # Preserve every required symbol while omitting another original import.
            h.write(table, {library: names for library, names in IMPORTS.items() if library != "kernel32.dll"})
            report["evidenceFiles"] = h.evidence_files(directory)
            with self.assertRaisesRegex(ValueError, "differs from the original native build"):
                h.replay(directory, report)
            # Even a self-consistent original report cannot qualify a PE missing a reviewed call.
            h.write(table, {library: names for library, names in IMPORTS.items() if library != "propsys.dll"})
            raw_build = directory / "native-build.json"
            build = json.loads(raw_build.read_bytes())
            build["evidenceFiles"][table.name] = h.sha(table)
            h.write(raw_build, build)
            report.update(evidenceFiles=h.evidence_files(directory), earlyResultSha256=h.sha(raw_build))
            with self.assertRaisesRegex(ValueError, "lacks the reviewed Windows"):
                h.replay(directory, report)

    def test_positive_read_requires_exact_history_phase_in_each_independent_log(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            run, report = trial(directory=directory)
            run()
            inspect = next(proc for proc in report["processes"] if proc["operation"] == "inspect")
            log = directory / inspect["log"]
            for replacement in (b"", b"phase=content\n", b"phase=history\nphase=history\n"):
                with self.subTest(replacement=replacement):
                    original = log.read_bytes()
                    log.write_bytes(original.replace(b"phase=history\n", replacement))
                    inspect["logSha256"] = h.sha(log)
                    report["evidenceFiles"] = h.evidence_files(directory)
                    with self.assertRaisesRegex(ValueError, "history-read phase"):
                        h.replay(directory, report)
                    log.write_bytes(original)

    def test_positive_replay_requires_ordinary_default_desktop_and_original_session(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            run, report = trial(directory=directory)
            run()
            for field, value in (("inputDesktop", "Private"), ("windowStation", "Other"),
                                 ("activeConsoleSession", 3), ("wts", dict(session=2, connectionState=0, lockFlags=0)),
                                 ("threadReceivesInput", False)):
                with self.subTest(field=field):
                    changed = deepcopy(report)
                    changed["desktop"][field] = value
                    h.write(directory / "desktop.json", changed["desktop"])
                    changed["evidenceFiles"] = h.evidence_files(directory)
                    with self.assertRaisesRegex(ValueError, "unlocked Default"):
                        h.replay(directory, changed)
            changed = deepcopy(report)
            changed["desktop"].update(session=3, activeConsoleSession=3)
            changed["desktop"]["wts"]["session"] = 3
            h.write(directory / "desktop.json", changed["desktop"])
            changed["evidenceFiles"] = h.evidence_files(directory)
            with self.assertRaisesRegex(ValueError, "Missing native process"):
                h.replay(directory, changed)

    def test_removing_both_rows_cannot_pass_as_selective_removal(self):
        run, report = trial({"broadRemoval": True})
        with self.assertRaisesRegex(RuntimeError, "exact toast cleanup"):
            run()
        self.assertTrue(report["finallyEmpty"])

    def test_unconfirmed_cleanup_fails_even_if_both_messages_delivered(self):
        run, report = trial({"ignoreRemoval": True})
        with self.assertRaisesRegex(RuntimeError, "exact toast cleanup"):
            run()
        self.assertNotIn("finallyEmpty", report)

    def test_show_success_without_history_is_unavailable(self):
        run, report = trial({"silentDrop": True})
        with self.assertRaises(h.Unavailable):
            run()
        self.assertEqual(report["modes"]["quiet"], dict(sent=True, observed=[]))
        self.assertTrue(report["finallyEmpty"])

    def test_disabled_setting_does_not_attempt_cleanup_or_show(self):
        run, report = trial({"setting": "3"})
        with self.assertRaises(h.Unavailable):
            run()
        self.assertFalse(any(p["operation"].startswith("remove") for p in report["processes"]))
        self.assertEqual(report["modes"]["normal"], dict(sent=False, observed=[]))

    def test_parser_rejects_another_process_and_duplicate_content(self):
        raw = (f"operation=inspect\naumid=IFW.RustQA.Toast.{TOKEN}\nphase=identity\npid=12\n"
               "session=3\nelevated=false\nphase=shortcut\ninstalledLinkVerified=true\nphase=history\ncount=0\n").encode()
        with self.assertRaisesRegex(ValueError, "process"):
            h.parse_log(raw, "inspect", TOKEN, 23, 3, 0)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            h.parse_log(raw + b"count=0\n", "inspect", TOKEN, 12, 3, 0)

    def test_native_notifier_errors_identify_the_exact_pre_show_call(self):
        prefix = (f"operation=post-quiet\naumid=IFW.RustQA.Toast.{TOKEN}\nphase=identity\npid=12\n"
                  "session=2\nelevated=true\nphase=shortcut\ninstalledLinkVerified=true\n")
        def parse(log, hr):
            raw = (prefix + log + f"Probe HRESULT {hr}\n").encode()
            return h.parse_log(raw, "post-quiet", TOKEN, 12, 2, 1, require_readiness=True)
        denied = -(1 << 31) + 0x70005
        for stage in ("create", "setting"):
            first = "phase=notifier-create\nready.1.create="
            log = first + ("" if stage == "create" else "0\nphase=notifier-setting\nready.1.setting=")
            record = parse(log + str(denied) + "\n", denied)
            self.assertEqual(record["notifierReadiness"][-1][stage], denied)
            with self.assertRaises(ValueError):
                parse(log + str(denied) + "\nphase=notifier-create\nready.2.create=" + str(h.NOT_FOUND) + "\n", h.NOT_FOUND)
        absent = "".join(f"phase=notifier-create\nready.{n}.create={h.NOT_FOUND}\n"
                         for n in range(1, h.MAX_NOTIFIER_ATTEMPTS + 1))
        self.assertEqual(len(parse(absent, h.NOT_FOUND)["notifierReadiness"]), h.MAX_NOTIFIER_ATTEMPTS)
        with self.assertRaises(ValueError):
            parse(absent + f"phase=notifier-create\nready.{h.MAX_NOTIFIER_ATTEMPTS+1}.create={h.NOT_FOUND}\n", h.NOT_FOUND)
        with self.assertRaisesRegex(ValueError, "immediate notifier"):
            parse(f"phase=notifier-create\nphase=notifier-create\nready.1.create={h.NOT_FOUND}\nready.2.create={h.NOT_FOUND}\n", h.NOT_FOUND)
        for invalid in ("Probe HRESULT -6441991024\n", "Probe HRESULT -2147023728\nextra=after-error\n"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "HRESULT"):
                h.parse_log((prefix + "phase=show\n" + invalid).encode(), "post-quiet", TOKEN, 12, 2, 1)

    def test_modern_native_receipts_replay_retry_and_one_show_per_sender(self):
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            run, report = trial(directory=d)
            run()
            build_path = d / "native-build.json"
            build = json.loads(build_path.read_bytes())
            build["sourceFiles"][h.READINESS_SOURCE] = "3" * 64
            build["steps"]["notifier-readiness"] = 0
            h.write(build_path, build)
            report.update(observerInputs=build["sourceFiles"], earlyResultSha256=h.sha(build_path))
            create_failed = f"phase=notifier-create\nready.1.create={h.NOT_FOUND}\n"
            setting_failed = f"phase=notifier-create\nready.2.create=0\nphase=notifier-setting\nready.2.setting={h.NOT_FOUND}\n"
            resolved = "phase=notifier-create\nready.3.create=0\nphase=notifier-setting\nready.3.setting=0\n"
            for proc in report["processes"]:
                if proc["operation"].startswith("post-"):
                    path = d / proc["log"]
                    path.write_bytes(path.read_bytes().replace(b"phase=notifier\n",
                                     (create_failed + setting_failed + resolved).encode()))
                    proc["logSha256"] = h.sha(path)
                    proc["notifierReadiness"] = [{"create": h.NOT_FOUND}, {"create": 0, "setting": h.NOT_FOUND},
                                                 {"create": 0, "setting": 0}]
            report["evidenceFiles"] = h.evidence_files(d)
            self.assertTrue(h.replay(d, report)["finallyEmpty"])
            proc = next(p for p in report["processes"] if p["operation"] == "post-normal")
            path = d / proc["log"]
            original = path.read_bytes()
            for replacement in (b"phase=show\nphase=show\n", b""):
                path.write_bytes(original.replace(b"phase=show\n", replacement))
                proc["logSha256"] = h.sha(path)
                report["evidenceFiles"] = h.evidence_files(d)
                with self.assertRaisesRegex((RuntimeError, ValueError), "readiness|cleanup"):
                    h.replay(d, report)
            path.write_bytes(original)
            proc["logSha256"] = h.sha(path)
            report["evidenceFiles"] = h.evidence_files(d)
            proc["notifierReadiness"].pop(0)
            with self.assertRaisesRegex((RuntimeError, ValueError), "readiness|cleanup"):
                h.replay(d, report)

    def test_recognizes_group_tag_and_both_exact_title_fields(self):
        clean = item("inspect", {"normal"}, {})["fields"]
        self.assertEqual(h.observed_rows(clean, TOKEN), {"normal"})
        for key in ("normal.tag", "normal.group", "normal.title", "normal.body", "count"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                h.observed_rows({**clean, key: "another notification"}, TOKEN)
