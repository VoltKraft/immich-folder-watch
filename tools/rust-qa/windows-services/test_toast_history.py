"""Regression controls for inbox notification history, selective removal and archived readback."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import toast_history as h

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

    def test_recognizes_group_tag_and_both_exact_title_fields(self):
        clean = item("inspect", {"normal"}, {})["fields"]
        self.assertEqual(h.observed_rows(clean, TOKEN), {"normal"})
        for key in ("normal.tag", "normal.group", "normal.title", "normal.body", "count"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                h.observed_rows({**clean, key: "another notification"}, TOKEN)
