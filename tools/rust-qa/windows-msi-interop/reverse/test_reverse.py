"""Portable controls for the detached original-window, connected-pipe and WPF quit checks."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import subprocess
from unittest.mock import Mock, patch
from hashlib import sha256
import unittest

from evidence import QUIT_SOURCE, activation_desktop, pipe_and_window, sha, shutdown, verify_prequit, worker_files
import private_desktop
import common
from reverse.observe import capture_quit_refusal


def sample():
    events = [dict(hwnd=70, event=what, root=True, winEventTimeMs=t) for what,t in (("show", 1), ("hide", 3), ("show", 3))]
    return dict(primary=dict(pid=11, created=100, arguments=[], sha256="wpf"), root=dict(hwnd=70, tid=150, pid=11),
                secondary=dict(pid=31, created=180, arguments=[], sha256="rust", exit=0, total=1, active=0, empty=True,
                               releaseQpc=200, cursor=2, releaseTick=3, resumedTick=3,
                               afterResume=dict(hwnd=70, pid=11, tid=150, created=100, cursorBefore=2, cursorAfter=2,
                                                beginQpc=202, endQpc=203, beginTick=3, endTick=3, visible=False)),
                showOrder="original HWND hidden after resume", frequency=10000, events=events, lifetimes=[[70, "create", 1]],
                before=dict(qpc=160, hwnd=70, visible=False, job=[11]), after=dict(qpc=220, observedTick=9, hwnd=70, visible=True, job=[11], created=100))


LOG = """MSI_REVERSE_CONNECTED client=31 server=11 created=100
MSI_REVERSE_SENT server=11 bytes=8
LAUNCHER_FOREGROUND_GRANT server=11 state=denied hresult=-5
LAUNCHER_SECONDARY server=11
"""


class ReverseTests(unittest.TestCase):
    def test_same_timestamp_requires_actual_show_after_the_suspended_process_cursor(self):
        row = sample()
        self.assertEqual(pipe_and_window(row, LOG, "wpf", "rust")["hwnd"], 70)
        visible_tie = copy.deepcopy(row)
        visible_tie["secondary"]["afterResume"]["visible"] = True
        with self.assertRaisesRegex(ValueError, "tied native SHOW"):
            pipe_and_window(visible_tie, LOG, "wpf", "rust")
        visible_tie["events"][-1]["winEventTimeMs"] = 4
        visible_tie["showOrder"] = "distinct native ticks"
        self.assertEqual(pipe_and_window(visible_tie, LOG, "wpf", "rust")["order"], "distinct native ticks")
        for key, bad in (("cursor", 3), ("total", 2), ("created", 100), ("arguments", ["--background"]), ("releaseQpc", 140)):
            with self.subTest(key=key):
                altered = copy.deepcopy(row)
                altered["secondary"][key] = bad
                with self.assertRaises(ValueError):
                    pipe_and_window(altered, LOG, "wpf", "rust")
        for key, value in (("hwnd", 74), ("root", False), ("event", "hide")):
            altered = copy.deepcopy(row)
            altered["events"][-1][key] = value
            with self.assertRaises(ValueError):
                pipe_and_window(altered, LOG, "wpf", "rust")
        row["lifetimes"] += [[70, "destroy", 3], [70, "create", 3]]
        with self.assertRaisesRegex(ValueError, "undestroyed"):
            pipe_and_window(row, LOG, "wpf", "rust")

    def test_private_reopen_requires_the_same_hidden_window_profile_process_and_native_times(self):
        name = "IfwQa_" + "a" * 32
        row = sample()
        state = dict(windowStation="WinSta0", stationVisible=True, session=2, activeConsoleSession=2,
                     wts=dict(session=2, connectionState=0, lockFlags=1), threadDesktop=name, inputDesktop=name,
                     threadReceivesInput=True, inputObjectReceivesInput=True)
        def point(begin, hidden=False):
            result = dict(desktop=name, receivesInput=True, observerPid=15, context=state, root=row["root"],
                          beginQpc=begin, endQpc=begin + 1,
                          surfaces=dict(witnessCount=1, rootCount=int(not hidden), otherVisible=0))
            if hidden:
                result.update(visible=False, membership=1)
            return result
        row.update(profile="a" * 32, stagedProfile=dict(inventoryToken="a" * 32), privateRoot=point(140),
                   hiddenDesktop=point(181, hidden=True), beforeQuitDesktop=point(225), desktopBefore=state,
                   desktopAfter=state, quit=dict(issuedQpc=240, exitedQpc=260, jobDrainedQpc=262), mutexReleasedQpc=270)
        for proc in (row["primary"], row["secondary"]):
            proc["machine"] = [0xaa64, 0xaa64]
        report = dict(target=private_desktop.ARM, desktopMode=private_desktop.MODE)
        selection = dict(name=name, session=2, originalRestored=True)
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            for file in ("private-desktop.json", "private-worker.json", "desktop-start.json"):
                (out / file).write_text("{}")
            # The separate desktop tests verify supervisor restoration, worker exit and both job handles.
            with patch.object(private_desktop, "replay", return_value=selection) as supervisor:
                self.assertEqual(activation_desktop(out, report, row, LOG, completed=False), selection)
                supervisor.assert_called_once_with(out, report, row, [])
                self.assertEqual(activation_desktop(out, report, row, LOG, completed=True), selection)
                supervisor.assert_called_with(out, report, row, [row])
                for obj, changes in (
                        (row["hiddenDesktop"], {"membership":0}), (row["hiddenDesktop"], {"visible":True}),
                        (row["hiddenDesktop"], {"root":{**row["root"], "hwnd":78}}),
                        (row["hiddenDesktop"], {"endQpc":205}), (row["beforeQuitDesktop"], {"beginQpc":200}),
                        (row["beforeQuitDesktop"]["surfaces"], {"otherVisible":1}),
                        (row["quit"], {"issuedQpc":215}), (row, {"mutexReleasedQpc":258}), (row["stagedProfile"], {"inventoryToken":"b"*32}),
                        (row["secondary"], {"machine":[0x8664, 0x8664]})):
                    with self.subTest(changes=changes), patch.dict(obj, changes), self.assertRaises(ValueError):
                        activation_desktop(out, report, row, LOG, completed=True)
                with self.assertRaisesRegex(ValueError, "Rust input desktop"):
                    activation_desktop(out, report, row, LOG.replace("denied hresult=-5", "unavailable reason=input-desktop"), completed=False)
                with self.assertRaisesRegex(ValueError, "activation desktop"):
                    activation_desktop(out, {"target":report["target"]}, row, LOG, completed=False)

    def test_cli_disallows_substitution_between_default_and_private_in_both_modes(self):
        from reverse.readback import replay
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            for reported, requested in (({}, True), ({"desktopMode":private_desktop.MODE}, False)):
                (out / "result.json").write_text(json.dumps(dict(direction="wpf-primary", **reported)))
                for partial in (True, False):
                    with self.subTest(partial=partial, requested=requested), self.assertRaisesRegex(ValueError, "desktop modes differ"):
                        replay(out, partial, requested)

    def test_native_checkout_hash_is_bound_to_git_with_only_known_eol_conversion(self):
        paths = ["tools/RustCompatibilityOracle/installed/windows.ps1", "tools/rust-qa/windows-msi-interop/launcher.patch"]
        revision = subprocess.check_output(["git","rev-parse","HEAD"], cwd=common.ROOT, text=True).strip()
        blobs = [subprocess.check_output(["git","show",f"{revision}:{name}"], cwd=common.ROOT) for name in paths]
        raw = {name:sha256(blob).hexdigest() for name, blob in zip(paths,blobs)}
        crlf = {name:sha256(blob.replace(b"\n", b"\r\n")).hexdigest() for name,blob in zip(paths,blobs)}
        with patch.object(common, "inputs", return_value=raw):
            common.verify_source_inputs({**raw, paths[0]:crlf[paths[0]]}, revision)
            with self.assertRaisesRegex(ValueError, "committed bytes"):
                common.verify_source_inputs(crlf, revision)
            with self.assertRaisesRegex(ValueError, "committed bytes"):
                common.verify_source_inputs({**raw, paths[0]:"00" * 32}, revision)

    def test_peer_and_process_creation_must_be_bound_to_the_actual_send(self):
        for bad in (LOG.replace("created=100", "created=101"), LOG.replace("client=31", "client=11"),
                    LOG.replace("SENT server=11", "SENT server=12"), LOG.replace("bytes=8", "bytes=0"),
                    LOG.replace("MSI_REVERSE_CONNECTED", "PIPE_DISCOVERY"), LOG + "LAUNCHER_PRIMARY pid=31\n"):
            with self.assertRaisesRegex(ValueError, "connected pipe"):
                pipe_and_window(sample(), bad, "wpf", "rust")

    def test_quit_refusal_preserves_uncertain_helper_cleanup_through_exception_chains(self):
        recorder = common.module("reverse_test_cleanup_type", common.QA / "windows-performance/native.py")
        uncertain = recorder.CleanupUnconfirmed("private Quit helper job is still active")
        wrapped = OSError("could not close test job")
        wrapped.__cause__ = uncertain
        contextual = RuntimeError("failed to finish measurement")
        contextual.__context__ = wrapped
        for error in (uncertain, wrapped, contextual):
            receipt, reap = {}, Mock()
            with self.subTest(error=error), self.assertRaises(type(error)) as caught:
                with capture_quit_refusal(recorder, receipt, reap):
                    raise error
            self.assertIs(caught.exception, error)
            self.assertEqual(receipt, {})
            reap.assert_not_called()
        receipt, reap = {}, Mock(return_value={"method":"owned process terminated after sampling", "exitCode":1})
        with capture_quit_refusal(recorder, receipt, reap):
            raise ValueError("The original WPF root did not own the menu point")
        self.assertEqual(receipt, dict(method="owned cleanup", error="The original WPF root did not own the menu point",
                                       cleanup=reap.return_value))
        reap.assert_called_once_with()

    def test_real_quit_provider_and_worker_drain_are_separate(self):
        messages = ["Folder watcher started with 1 source(s).", "Flushing pending uploads before shutdown."]
        row = sample()
        q = row["quit"] = dict(receiver=135, tid=150, issuedQpc=230, exitedQpc=260, method="shipping tray Quit", exit=0, empty=True)
        menu = dict(status="invoked", pid=11, created=100, receiver=135, tid=150, menuHwnd=170,
                    sourceSha256=QUIT_SOURCE, rawInteraction="tray-menu-quit; popup=170; verifiedHighlightedCommandId=3; nativeMouseClick")
        hit = dict(hwnd=70, root=70, pid=11, tid=150, rootPid=11, rootTid=150)
        point = dict(x=301, y=172)
        menu.update(root=70, stage="original-close", anchor=dict(dpiContext="per-monitor-v2", clientRect=dict(left=1, top=22, right=401, bottom=222),
                    point=point, before=hit, after=hit, cursor=point, physicalCursor=point, probes=[hit]))
        suffix = "info: ImmichFolderWatch.Core.Services.FolderWatchWorker[0] Flushing pending uploads before shutdown."
        self.assertTrue(shutdown(row, messages, menu, suffix)["flushStarted"])
        self.assertEqual(shutdown(row, messages, menu, suffix)["flushCompletion"], "unobserved")
        self.assertFalse(shutdown(row, messages, menu, "")["flushStarted"])
        self.assertFalse(shutdown(row, messages[:1], menu, suffix)["flushStarted"])
        missing = {k: v for k, v in menu["anchor"].items() if k != "probes"}
        with self.assertRaisesRegex(ValueError, "tray menu anchor"):
            shutdown(row, messages, {**menu, "anchor": missing}, suffix)
        exposed = dict(x=201, y=172)
        alternate = {**menu["anchor"], "probes": [{**hit, "root": 99}, hit],
                     "point": exposed, "cursor": exposed, "physicalCursor": exposed}
        self.assertTrue(shutdown(row, messages, {**menu, "anchor": alternate}, suffix)["orderlyProcessExit"])
        for probes in ([], [hit, hit], [hit, {**hit, "hwnd": 99}], [hit] * 17):
            with self.assertRaisesRegex(ValueError, "tray menu anchor"):
                shutdown(row, messages, {**menu, "anchor": {**alternate, "probes": probes}}, suffix)
        for override in ({"physicalCursor": dict(x=300, y=172)}, {"after": {**hit, "root": 71}}, {"before": {**hit, "rootPid": 19}},
                         {"point": dict(x=401, y=222)}, {"dpiContext": "virtualized"}):
            with self.assertRaisesRegex(ValueError, "tray menu anchor"):
                shutdown(row, messages, {**menu, "anchor": {**menu["anchor"], **override}}, suffix)
        for key, bad in (("menuHwnd", 0), ("menuHwnd", 171), ("status", "incomplete"), ("pid", 99),
                         ("sourceSha256", "other"), ("rawInteraction", menu["rawInteraction"].replace("Id=3", "Id=2"))):
            with self.assertRaises(ValueError):
                shutdown(row, messages, {**menu, key: bad}, suffix)
        q.update(method="owned cleanup", error="menu unavailable", cleanup={"method":"owned process terminated after sampling"})
        self.assertFalse(shutdown(row, messages, {}, suffix)["orderlyProcessExit"])
        q["empty"] = False
        with self.assertRaises(ValueError):
            shutdown(row, messages, {}, suffix)

    def test_partial_artifact_replays_activation_before_any_quit_or_uninstall_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            row = sample()
            row["primary"]["image"] = "WPF"
            row.update(status="reactivated", revision="abc", target="native",
                       desktopBefore=dict(windowStation="WinSta0", stationVisible=True, session=2, activeConsoleSession=2,
                                          wts=dict(session=2, connectionState=0, lockFlags=1), threadDesktop="Default",
                                          inputDesktop="Default", inputObjectReceivesInput=True, threadReceivesInput=True))
            (out / "rust.log").write_text(LOG)
            original = b"Folder watcher started with 1 source(s).\n" + 2 * b"Persistent reconciliation for uploadNew queued 0 changed file(s) from photos.\n"
            (out / "wpf-before-quit.log").write_bytes(original)
            (out / "wpf.log").write_bytes(original + b"other later lines\n")
            row.update(rustLog=sha(out / "rust.log"), wpfPrefix=sha(out / "wpf-before-quit.log"))
            (out / "before-quit.json").write_text(json.dumps(row))
            args = (out, dict(revision="abc", target="native", wpfProfile={"media":"photos"}), dict(application=dict(sha256="rust")),
                    dict(exe="WPF", exeSha256="wpf"))
            self.assertEqual(verify_prequit(*args)["hwnd"], 70)
            for field, other in (("inputDesktop", "Other"), ("threadDesktop", "Other"), ("activeConsoleSession", 3)):
                with self.subTest(field=field), patch.dict(row["desktopBefore"], {field:other}):
                    (out / "before-quit.json").write_text(json.dumps(row))
                    with self.assertRaisesRegex(ValueError, "unlocked input session"):
                        verify_prequit(*args)
            (out / "before-quit.json").write_text(json.dumps(row))
            (out / "wpf.log").unlink()
            self.assertEqual(verify_prequit(*args)["hwnd"], 70)
            (out / "wpf.log").write_bytes(b"another run")
            with self.assertRaisesRegex(ValueError, "pre-Quit observation"):
                verify_prequit(*args)

    def test_read_only_sqlite_and_source_records_require_the_original_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            folder = out / "wpf-profile"
            logs = folder / "engine-logs"
            logs.mkdir(parents=True)
            db = folder / "sync-state.db"
            with sqlite3.connect(db) as cx:
                for table in ("sync_entries", "owned_albums", "sync_timestamp_repairs"):
                    cx.execute(f"CREATE TABLE {table}(id INTEGER PRIMARY KEY)")
            cx.close()
            entry = logs / "immich-folder-watch-20261126.log"
            line = "2026-11-26 10:02:31.402 +00:00 [Information] ImmichFolderWatch.Core.Services.FolderWatchWorker: "
            entry.write_text(line + "Folder watcher started with 1 source(s).\n", encoding="utf-8")
            expected = {"sync-state.db":sha(db), entry.relative_to(folder).as_posix():sha(entry)}
            self.assertEqual(worker_files(out, expected), ["Folder watcher started with 1 source(s)."])
            self.assertEqual(sorted(x.name for x in folder.iterdir()), ["engine-logs","sync-state.db"])
            with sqlite3.connect(db) as cx:
                cx.execute("INSERT INTO sync_entries DEFAULT VALUES")
            cx.close()
            with self.assertRaisesRegex(ValueError, "profile differs"):
                worker_files(out, expected)
            with self.assertRaisesRegex(ValueError, "empty synthetic"):
                worker_files(out, {**expected, "sync-state.db":sha(db)})


if __name__ == "__main__":
    unittest.main()
