import unittest

from run import verified_edit


class ReaderEditTests(unittest.TestCase):
    def record(self, through=False):
        name = "Grüße – Sommer.jpg"
        selected = dict(value=name, document=name, selected=name, selectionCount=1,
                        selectionStart=0, selectionEnd=len(name), documentCollapsed=False)
        empty = dict(value="", document="", valueLength=0, documentLength=0, documentCollapsed=True)
        route = "nvdaPassThroughDelete" if through else "ordinaryDelete"
        states = {key: selected.copy() for key in ("selectedForCopy", "selectedForDelete", "pasted")}
        if through:
            states.update({key: selected.copy() for key in ("ordinaryDelete", "selectedForPassThrough",
                                                            "afterPassAnnouncement")})
        states[route] = empty
        return dict(readerEdit=dict(clearedBy=route, states=states), clipboardCopied=True, unicodeClipboardRoundTrip=True)

    def test_native_routes_are_reported_separately(self):
        self.assertEqual(verified_edit(self.record(), False), "ordinaryDelete")
        self.assertEqual(verified_edit(self.record(through=True), True), "nvdaPassThroughDelete")

    def test_nonempty_or_nondegenerate_document_fails(self):
        for key, value in (("value", "x"), ("document", "x"), ("documentLength", 18), ("documentCollapsed", False)):
            with self.subTest(key=key):
                record = self.record()
                record["readerEdit"]["states"]["ordinaryDelete"][key] = value
                with self.assertRaisesRegex(ValueError, "empty text"):
                    verified_edit(record, False)

    def test_pass_command_requires_acknowledgement_and_current_full_selection(self):
        record = self.record(through=True)
        with self.assertRaisesRegex(ValueError, "NVDA's speech"):
            verified_edit(record, False)
        record["readerEdit"]["states"]["afterPassAnnouncement"]["selectionEnd"] -= 1
        with self.assertRaisesRegex(ValueError, "selected"):
            verified_edit(record, True)

    def test_unchanged_source_and_unicode_restoration_are_both_required(self):
        record = self.record(through=True)
        record["readerEdit"]["states"]["ordinaryDelete"]["document"] = ""
        with self.assertRaisesRegex(ValueError, "ordinary Delete outcome"):
            verified_edit(record, True)
        record = self.record()
        record["readerEdit"]["states"]["pasted"]["value"] = "Grusse - Sommer.jpg"
        with self.assertRaisesRegex(ValueError, "Unicode filename"):
            verified_edit(record, False)
