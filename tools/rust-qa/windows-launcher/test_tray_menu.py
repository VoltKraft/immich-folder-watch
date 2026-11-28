"""Control the physical menu readback, existing tray ownership and two-worker evidence offline."""
from copy import deepcopy
import unittest

import native_tray as tray
import tray_menu
from tray_menu_input import expected_menus, identify_menu
from test_native_tray import COMPLEMENT, ELEMENT, KEY, SURFACE, TOKEN, registration, closed


def rows(language="en"):
    labels = expected_menus(tray_menu.RESOURCES)[language]
    items = []
    for i, text in enumerate(labels):
        if i:
            items.append(dict(text="", separator=True))
        items.append(dict(text=text, id=i+1, separator=False, enabled=True, left=1, right=120, top=i*20, bottom=i*20+18))
    return items


class NativeMenuTests(unittest.TestCase):
    def test_open_requires_foreground_and_keyboard_focus_on_original_editor(self):
        surface = dict(hwnd="0x12", pid=23, tid=31)
        sample = dict(thread=31, foreground=True, active=True, focused=True, queryError=0)
        evidence = dict(hwnd=18, pid=23, observed=True, applicable=True, sameWindowVisible=True, samples=1, lastSample=sample)
        tray_menu.verify_focus(surface, evidence)
        for change in ({"hwnd":42}, {"pid":24}, {"sameWindowVisible":False}, {"samples":0},
                       *({"lastSample":{**sample,key:False}} for key in ("foreground","active","focused")),
                       {"lastSample":{**sample,"thread":33}}, {"lastSample":{**sample,"queryError":5}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                tray_menu.verify_focus(surface, {**evidence,**change})

    def test_replay_binds_raw_provider_events_both_physical_buttons_and_selected_identifier(self):
        labels = expected_menus(tray_menu.RESOURCES)
        second = {**SURFACE, "rgb": COMPLEMENT}
        ready = dict(stage="ready", surface=second, provider=ELEMENT)
        events = [dict(stage="baseline", pane=None, pid=81, bar=51, cursor=[4,3]),
                  dict(stage="first", surface=SURFACE), ready, {**ready, "stage":"attempt"},
                  {**ready, "stage":"menu-target", "action":"open"},
                  dict(stage="cleanup", attempted=False, baselineRead=True, iconAttempted=True, restored=False,
                       observedOpen=None, original=None, final=None, cursor=[4,3])]
        menu = dict(rows=rows(), language="en", hwnd=62, menu=71, tid=72, pid=18, receiver=43, menuOwner=43, popupOwner=None)
        icon = dict(root=51, hit=52, ownerPid=81, rect=SURFACE["rect"], colorref=int.from_bytes(bytes.fromhex(COMPLEMENT),"little"))
        selected = dict(hit=62, menu=71, ownerPid=18, id=1, text="Open GUI")
        right = dict(flags=[8,16], tag=777, queued=2, beginQpc=10, endQpc=12, point=[12,26], before=icon, atPoint=icon)
        left = dict(flags=[2,4], tag=777, queued=2, beginQpc=18, endQpc=19, point=[60,9], before=selected, atPoint=selected)
        state = dict(menu=menu, surface=second, iconProvider=ELEMENT, pointerRestored=True, contextClick=right, commandClick=left,
                     opened=dict(event="opened", language="en", point=[12,26]))
        self.assertEqual(tray_menu.verify_gesture("open",state,KEY,101,TOKEN,events,labels)[1], dict(event="selected",action="open"))
        for change in ({"menu":{**menu, "menuOwner":92}}, {"commandClick":{**left, "atPoint":{**selected,"id":3}}},
                       {"contextClick":{**right, "queued":1}}, {"pointerRestored":False}, {"menu":{**menu,"language":"de"}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                tray_menu.verify_gesture("open",{**state,**change},KEY,101,TOKEN,events,labels)

    def test_actual_shipping_resources_and_native_command_ids_and_separators(self):
        expected = expected_menus(tray_menu.RESOURCES)
        self.assertEqual(expected, dict(en=["Open GUI", "Restart", "Quit"], de=["GUI öffnen", "Neustart", "Beenden"]))
        for lang in expected:
            self.assertEqual(identify_menu(rows(lang), expected), lang)
        for index, changed in ((0, dict(id=3)), (1, dict(separator=False)), (2, dict(text="Unknown")),
                               (3, dict(text="Different")), (4, dict(enabled=False)), (4, dict(right=1))):
            candidate = rows()
            candidate[index].update(changed)
            with self.subTest(change=changed), self.assertRaises(ValueError):
                identify_menu(candidate, expected)

    def test_context_event_requires_original_receiver_and_real_action(self):
        opened = "TRAY_MENU_OPENED pid=18 hwnd=43 id=23 x=-22 y=87 language=de\n"
        chosen = "TRAY_MENU_SELECTED pid=18 hwnd=43 id=23 action=restart\n"
        self.assertEqual(tray_menu.messages(opened+chosen,*KEY[:2]), [
            dict(event="opened", point=[-22,87], language="de"), dict(event="selected", action="restart")])
        for bad in (opened.replace("id=23", "id=14"), chosen.replace("43","75"), chosen.replace("restart","other")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tray_menu.messages(bad,*KEY[:2])

    def test_two_pinned_worker_lifetimes_have_separate_exit_and_completion_receipts(self):
        events = ["INVENTORY_WORKER pid=11", "WORKER_EXIT pid=11 reason=restart success=true",
                  "INVENTORY_WORKER pid=22", "WORKER_RESTARTED old=11 new=22", "WORKER_EXIT pid=22 reason=quit success=true",
                  "CONTROL_READER_STOPPED", "DRAINED passes=12"]
        self.assertEqual(tray_menu.lifecycle("\n".join(events)+"\n",11,22),events[:-1])
        for bad in (events[:-2]+events[-1:], events[:4]+events[4:5]*2+events[5:],
                    events[:1]+list(reversed(events[1:3]))+events[3:], [s.replace("success=true","success=false") for s in events]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tray_menu.lifecycle("\n".join(bad)+"\n", 11,22)

    def test_real_nim_setfocus_does_not_change_icon_ownership(self):
        working = f"LAUNCHER_PRIMARY pid={KEY[0]}\n" + registration(True)
        done = closed(True)
        for result in ("true", "false"):
            observations = {}
            tray.replay_shutdown(working + "gui_tray.menu.focus="+result+"\n" + done, KEY, TOKEN, observations)
            self.assertEqual(observations["reportedCleanupMethod"], "deletedAtQuit")
        with self.assertRaises(tray.CleanupUnconfirmed):
            tray.replay_shutdown(f"LAUNCHER_PRIMARY pid={KEY[0]}\n" + registration(False) + "gui_tray.menu.focus=true\n" +
                                 closed(False), KEY, TOKEN, {})
