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
from zipfile import ZipFile

import toast_history as h
import toast_display_name as registration
import toast_banner as banner
from test_notification import trace

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


def direct_report(directory):
    run, report = trial(directory=directory)
    run()
    native = directory / "native-build.json"
    build = json.loads(native.read_bytes())
    build["sourceFiles"][h.READINESS_SOURCE] = "3" * 64
    build["steps"]["notifier-readiness"] = 0
    h.write(native, build)
    report.update(observerInputs=build["sourceFiles"], earlyResultSha256=h.sha(native))
    for proc in report["processes"]:
        op = proc["operation"]
        if not op.startswith("post-"):
            continue
        quiet = op == "post-quiet"
        # One sender has an unavailable setting; the other reads Enabled.
        code = h.NOT_FOUND if quiet else 0
        setting = "unavailable" if quiet else "0"
        proc["notifierReadiness"] = [dict(create=0, setting=code)]
        proc["postResult"] = dict(setting=setting, showHresult=0)
        name = directory / proc["log"]
        raw = (f"operation={op}\naumid=IFW.RustQA.Toast.{TOKEN}\nphase=identity\npid={proc['pid']}\n"
               "session=2\nelevated=true\nphase=shortcut\ninstalledLinkVerified=true\n"
               f"phase=notifier-create\nready.1.create=0\nphase=notifier-setting\nready.1.setting={code}\n")
        if quiet:
            raw += "readinessElapsedMs=8000\n"
        raw += (f"setting={setting}\nphase=content\nsuppressPopup={str(quiet).lower()}\n"
                "mirroringDisabled=true\nexpirationTicks=12345\nphase=show\nshowHresult=0\nshowReturned=true\n")
        name.write_bytes(raw.encode())
        proc["logSha256"] = h.sha(name)
    report["evidenceFiles"] = h.evidence_files(directory)
    return report


class ToastBannerTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.receipt, _ = trace(2)
        self.match = deepcopy(self.rows[2]["match"])
        self.rows[2]["match"] = self.match
        self.match["title"] = dict(self.match["title"], text=f"IFW synthetic normal {TOKEN}")
        self.match["body"] = dict(self.match["body"], text=f"Rust normal notification history {TOKEN}")
        self.match["host"] = dict(self.match["host"], windowClass="Windows.UI.Core.CoreWindow")
        self.match["popup"] = dict(runtimeId="12,85", pid=34, shellPid=34, controlType="Window",
                                   automationId="NormalToastView", containerPath=["12,87", "12,85"])
        self.aumid = "IFW.RustQA.Toast." + TOKEN
        self.sender = dict(operation="post-normal", log="005-post-normal.txt", pid=25, creation100ns=123)
        self.receipt.update(aumid=self.aumid, senderIdentity=[25, 123], senderLog=self.sender["log"],
                            desktopBefore=deepcopy(DESKTOP), desktopAfter=deepcopy(DESKTOP), windowsDirectory=r"C:\Windows",
                            observer=dict(pid=26, creation100ns=122, machine=[0x8664] * 2, exit=0, jobEmpty=True))
        self.item = dict(phases=["show"], hresult=None, postResult=dict(showHresult=0),
                         fields=dict(operation="post-normal", aumid=self.aumid, suppressPopup="false", showHresult="0",
                                     showFrequency="1000", showBeginQpc="186", showEndQpc="202", showReturned="true"))

    def result(self):
        return banner.assess(self.receipt, self.rows, self.sender, self.item, 2, 0x8664)

    def test_normal_toast_visible_only_in_its_own_physical_popup_after_show_begins(self):
        self.assertEqual(self.result()["status"], "visible")
        self.assertEqual(self.result()["samplingWindow"]["acceptedSample"], 2)
        for changes in (dict(automationId="NotificationCenterToastViewDetails"), dict(containerPath=["12,413", "12,85"])):
            with self.subTest(changes=changes), patch.dict(self.match["popup"], changes), self.assertRaises(ValueError):
                self.result()
        del self.match["popup"]
        self.assertEqual(self.result()["status"], "unavailable")
        self.match["title"]["text"] = f"IFW synthetic quiet {TOKEN}"
        with self.assertRaises(ValueError):
            self.result()

    def test_wrong_shell_owner_wrong_sender_or_earlier_match_cannot_confirm(self):
        self.match["popup"]["shellPid"] = 42
        with self.assertRaises(ValueError):
            self.result()
        self.match["popup"]["shellPid"] = 34
        self.item["fields"]["showBeginQpc"] = "193"
        with self.assertRaises(ValueError):
            self.result()
        self.item["fields"]["showBeginQpc"] = "186"
        for key, wrong in (("aumid", "other"), ("senderIdentity", [25, 122]), ("senderLog", "004-post-quiet.txt")):
            with self.subTest(key=key), patch.dict(self.receipt, {key: wrong}), self.assertRaises(ValueError):
                self.result()
        self.receipt["desktopAfter"]["inputDesktop"] = "another"
        self.assertEqual(self.result()["status"], "unavailable")
        with patch.dict(self.receipt["observer"], jobEmpty=False), self.assertRaises(ValueError):
            self.result()

    def test_denial_suppression_and_unavailable_provider_give_no_presentation(self):
        for changes in ({"hresult": -1}, {"postResult": {"showHresult": None}},
                        {"fields": dict(self.item["fields"], suppressPopup="true")}):
            with self.subTest(changes=changes), patch.dict(self.item, changes):
                self.assertEqual(self.result()["status"], "unavailable")
        with patch.dict(self.sender, operation="post-quiet"), self.assertRaises(ValueError):
            self.result()
        with patch.dict(self.receipt["observer"], forced=True), self.assertRaises(ValueError):
            self.result()
        del self.receipt["observer"]
        self.rows.clear()
        self.assertEqual(self.result()["status"], "unavailable")

    def test_sender_still_runs_exactly_once_when_the_original_desktop_has_no_observer(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, SystemRoot=r"C:\Windows"), patch.object(
                banner, "select_powershell", return_value=(None, [])):
            folder = Path(directory)
            api, desktop = Mock(frequency=1000), Mock()
            api.clock.return_value = 400
            desktop.context.return_value = DESKTOP
            send = Mock(return_value=self.item)
            sender = self.sender | {"machine": (0x8664, 0x8664)}
            post, outcome = banner.observe(api, desktop, folder, {}, folder, 5, TOKEN, sender, send, 2)
            send.assert_called_once_with()
            self.assertIs(post, self.item)
            self.assertEqual(outcome["status"], "unavailable")
            files, original = banner.archived(folder, 5, sender, self.item, 2, 0x8664)
            self.assertEqual(files, {"005-normal-popup.json"})
            self.assertEqual(original, outcome)

    def test_armed_provider_runs_the_single_sender_under_the_native_directory_name_contract(self):
        from native import Win32
        with TemporaryDirectory() as directory, patch.dict(os.environ, SystemRoot=r"C:\Windows"):
            folder = Path(directory)
            api, desktop = Mock(frequency=1000), Mock()
            api.nt_create.return_value = 0
            api.clock.side_effect = [182, 210, 10230]
            desktop.context.return_value = DESKTOP
            controls = folder / ("ifw-rw02-" + TOKEN)

            @contextmanager
            def owned(api, parent, name):
                # Run the actual relative-name guard up to the first (mocked) native call.
                Win32.create_child_directory(api, 51, name)
                api.nt_create.assert_called_once()
                self.assertEqual(parent / name, controls)
                controls.mkdir()
                yield controls

            raw = folder / "005-normal-popup.log"
            def write_rows(rows):
                raw.write_text("".join("NOTICE_OBSERVER " + json.dumps(row) + "\n" for row in rows))

            @contextmanager
            def provider(api, program, args, area, env, log, record):
                self.assertEqual(log, raw)
                self.assertEqual(args[-2:], ["-Kind", "WinrtNormal"])
                write_rows(self.rows[:2])
                proc = Mock()
                proc.wait.side_effect = lambda *, timeout: self.assertEqual((controls / "notice.sent").read_text(), TOKEN)
                yield proc
                self.assertTrue((controls / "notice.finish").is_file())
                record.update(self.receipt["observer"])

            def post():
                self.assertTrue((controls / "notice.go").is_file())
                write_rows(self.rows)
                return self.item

            send = Mock(side_effect=post)
            sender = self.sender | {"machine": (0x8664, 0x8664)}
            with patch.object(banner, "select_powershell", return_value=("powershell.exe", [])), \
                    patch.object(banner, "owned_directory", owned), patch.object(banner, "child", provider), \
                    patch.object(banner, "wait_for_observer", return_value=True):
                _, observation = banner.observe(api, desktop, folder, {}, folder, 5, TOKEN, sender, send, 2)
            send.assert_called_once_with()
            self.assertEqual(observation["status"], "visible")
            _, original = banner.archived(folder, 5, sender, self.item, 2, 0x8664)
            self.assertEqual(observation, original)

    def test_replay_binds_new_observation_and_preserves_history_without_a_banner(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            report = direct_report(directory)
            native = directory / "native-build.json"
            build = json.loads(native.read_bytes())
            build["sourceFiles"][banner.SOURCE] = "5" * 64
            points = directory / "notification-points.txt"
            points.write_text("WinRT popup selection passed.\n")
            build["steps"]["notification-points"] = 0
            build["evidenceFiles"][points.name] = h.sha(points)
            h.write(native, build)
            report.update(observerInputs=build["sourceFiles"], earlyResultSha256=h.sha(native), historyStatus="passed")
            for index, proc in enumerate(report["processes"]):
                if not proc["operation"].startswith("post-"):
                    continue
                path = directory / proc["log"]
                raw = path.read_bytes().replace(b"showReturned=true", b"showFrequency=1000\nshowBeginQpc=186\nshowEndQpc=202\nshowReturned=true")
                path.write_bytes(raw)
                proc["logSha256"] = h.sha(path)
                if proc["operation"] == "post-normal":
                    name = f"{index:03}-normal-popup"
                    source = dict(self.receipt, senderLog=proc["log"], senderIdentity=[proc["pid"], proc["creation100ns"]],
                                  observerLog=name + ".log")
                    h.write(directory / (name + ".json"), source)
                    log = directory / (name + ".log")
                    log.write_text("".join("NOTICE_OBSERVER " + json.dumps(row) + "\n" for row in self.rows))
            report.update(presentationObserved=True, normalBanners=[self.result()], evidenceFiles=h.evidence_files(directory))
            self.assertTrue(h.replay(directory, report)["presentationObserved"])
            # Recompute every file digest after removing only the popup surface evidence.
            del self.match["popup"]
            log.write_text("".join("NOTICE_OBSERVER " + json.dumps(row) + "\n" for row in self.rows))
            report["evidenceFiles"] = h.evidence_files(directory)
            with self.assertRaises(ValueError):
                h.replay(directory, report)
            report.update(presentationObserved=None, normalBanners=[self.result()])
            replayed = h.replay(directory, report)
            self.assertEqual(replayed["historyStatus"], "passed")
            self.assertIsNone(replayed["presentationObserved"])
            self.assertTrue(replayed["finallyEmpty"])


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
        api.machine.return_value = (machine, machine)
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

    def test_isolated_vm_requires_an_original_digest_and_bounds_extraction(self):
        prefix = "native-" + TARGET + "/"
        with TemporaryDirectory() as temp:
            archive = Path(temp) / "sender.zip"
            report = dict(target=TARGET, hosted=True, runner="native-build", head="a" * 40, workflowRun="42",
                          workflowAttempt="1", evidenceFiles={"compiler.txt": h.hashlib.sha256(b"compiler").hexdigest()})
            with ZipFile(archive, "w") as bundle:
                bundle.writestr(prefix + "result.json", json.dumps(report))
                bundle.writestr(prefix + "compiler.txt", b"compiler")
                bundle.writestr("build/" + TARGET + "/release/" + h.toast_vm.EXE, b"PE fixture")
            with h.toast_vm.read_sender(archive, h.sha(archive)) as (exe, area, receipt):
                self.assertEqual((exe.read_bytes(), (area / "compiler.txt").read_bytes(), receipt),
                                 (b"PE fixture", b"compiler", report))
            self.assertFalse(exe.exists())
            with self.assertRaisesRegex(ValueError, "digest changed"), h.toast_vm.read_sender(archive, "0" * 64):
                self.fail("A changed archive reached the caller")
            with ZipFile(archive, "a") as bundle:
                bundle.writestr(prefix + "../elsewhere", b"unrecorded")
            with self.assertRaisesRegex(ValueError, "differs from the build receipt"), h.toast_vm.read_sender(archive, h.sha(archive)):
                self.fail("Unexpected archive entries reached the caller")
            with patch.object(sys, "platform", "win32"), patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                with self.assertRaisesRegex(ValueError, "disposable"):
                    h.toast_vm.require_vm(TARGET)

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
            build["sourceFiles"][h.READINESS_SOURCE] = h.SETTING_REQUIRED_SHA256
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

    def test_direct_show_requires_the_final_notifier_and_reports_its_exact_hresult(self):
        prefix = (f"operation=post-quiet\naumid=IFW.RustQA.Toast.{TOKEN}\nphase=identity\npid=12\n"
                  "session=2\nelevated=true\nphase=shortcut\ninstalledLinkVerified=true\n")
        created = "phase=notifier-create\nready.1.create=0\n"
        setting = "phase=notifier-setting\nready.1.setting="
        unknown = created + setting + f"{h.NOT_FOUND}\nreadinessElapsedMs=7520\nsetting=unavailable\n"
        properties = "phase=content\nsuppressPopup=true\nmirroringDisabled=true\nexpirationTicks=12345\n"
        shown = properties + "phase=show\nshowHresult=0\nshowReturned=true\n"
        denied = -2147024891

        def parse(log, hr=None):
            terminal = "" if hr is None else f"Probe HRESULT {hr}\n"
            return h.parse_log((prefix + log + terminal).encode(), "post-quiet", TOKEN, 12, 2,
                               int(hr is not None), require_readiness=True, direct_show=True)

        for value in (0, 1):
            row = parse(unknown + shown.replace("showHresult=0", f"showHresult={value}"))
            self.assertTrue(h.validate_post(row, "quiet"))
            self.assertEqual(row["postResult"], dict(setting="unavailable", showHresult=value))
        row = parse(unknown + properties + f"phase=show\nshowHresult={denied}\n", denied)
        self.assertEqual(row["postResult"], dict(setting="unavailable", showHresult=denied))
        for token in ("suppressPopup=true\n", "mirroringDisabled=true\n", "expirationTicks=12345\n"):
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, "properties before Show"):
                parse(unknown + properties.replace(token, "") + f"phase=show\nshowHresult={denied}\n", denied)
        with self.assertRaisesRegex(ValueError, "properties before Show"):
            parse(unknown + properties.replace("suppressPopup=true", "suppressPopup=false")
                  + f"phase=show\nshowHresult={denied}\n", denied)
        with self.assertRaisesRegex(ValueError, "original native Show return"):
            parse(unknown + "showReturned=true\n" + shown.replace("showReturned=true\n", ""))
        for blocked in ("1", "2", "3", "4"):
            raw = created + setting + f"0\nsetting={blocked}\n"
            row = parse(raw)
            self.assertFalse(h.validate_post(row, "quiet"))
            self.assertEqual(row["postResult"], dict(setting=blocked, showHresult=None))
            with self.assertRaises(ValueError):
                parse(raw + shown)
        for raw in (unknown.replace("7520", "200"), unknown.replace("7520", "-1"),
                    unknown.replace("ready.1.setting=" + str(h.NOT_FOUND), "ready.1.setting=" + str(denied)),
                    f"phase=notifier-create\nready.1.create={h.NOT_FOUND}\nreadinessElapsedMs=8000\nsetting=unavailable\n",
                    created + setting + f"{h.NOT_FOUND}\nsetting=0\n"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse(raw + shown)
        for raw, hr in ((shown.replace("showHresult=0\n", ""), None),
                        (shown.replace("showHresult=0", f"showHresult={denied}"), None),
                        (shown, denied), (shown.replace("showHresult=0", "showHresult=2147483648"), None),
                        (properties + "phase=show\n", denied)):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse(unknown + raw, hr)

    def test_direct_show_replay_requires_both_history_rows_and_independent_readback(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            report = direct_report(directory)
            self.assertTrue(h.replay(directory, report)["finallyEmpty"])
            for attr in ("presentationObserved", "activationObserved"):
                with self.subTest(attr=attr), self.assertRaises(ValueError):
                    h.replay(directory, {**report, attr: True})
            sender = next(p for p in report["processes"] if p["operation"] == "post-quiet")
            sender["postResult"]["showHresult"] = 1
            with self.assertRaisesRegex(RuntimeError, "exact toast cleanup") as rejected:
                h.replay(directory, report)
            self.assertIn("Show result", str(rejected.exception.__cause__))
            sender["postResult"]["showHresult"] = 0
            reader = next(p for p in report["processes"] if p["operation"] == "inspect"
                          and b"quiet.title" in (directory / p["log"]).read_bytes())
            path = directory / reader["log"]
            path.write_bytes(path.read_bytes().replace(b"IFW synthetic quiet", b"Different quiet"))
            reader["logSha256"] = h.sha(path)
            report["evidenceFiles"] = h.evidence_files(directory)
            with self.assertRaises((ValueError, RuntimeError)):
                h.replay(directory, report)

    def test_recognizes_group_tag_and_both_exact_title_fields(self):
        clean = item("inspect", {"normal"}, {})["fields"]
        self.assertEqual(h.observed_rows(clean, TOKEN), {"normal"})
        for key in ("normal.tag", "normal.group", "normal.title", "normal.body", "count"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                h.observed_rows({**clean, key: "another notification"}, TOKEN)
