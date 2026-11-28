"""Keep the optional ARM64 editor assessment separate from ordinary CI."""

from pathlib import Path
import re
import unittest


WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"
REGULAR = {"build-linux", "lint-flatpak", "validate-flatpak", "validate-pages-artifact"}
FLAG = "inputs.rw02_editor_arm64"
REWRITE = "github.ref == 'refs/heads/rewrite/rust'"


class UbuntuEditorWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (WORKFLOWS / "ci.yaml").read_text()
        cls.events, jobs = source.split("\njobs:\n")
        cls.jobs = dict(re.findall(r"^  ([\w-]+):\n(.*?)(?=^  [\w-]+:\n|\Z)", jobs, re.M | re.S))
        cls.editor = (WORKFLOWS / "rust-ubuntu-arm64-editor.yaml").read_text()

    def test_push_pr_and_default_dispatch_keep_the_regular_jobs(self):
        self.assertRegex(self.events, r"(?s)  workflow_dispatch:\n    inputs:\n      rw02_editor_arm64:\n.*?"
                                      r"        type: boolean\n        default: false\n")
        self.assertEqual(set(self.jobs), REGULAR | {"rw02-editor-arm64", "build-windows"})
        for name in REGULAR:
            self.assertEqual(self.jobs[name].splitlines()[0].strip(), f"if: ${{{{ !{FLAG} }}}}")
        # Push and pull_request have no dispatch inputs. The existing Windows
        # exclusions still apply to the rewrite ref and its same-repository PR.
        condition = self.jobs["build-windows"].split("    if: >-\n")[1].split("    name:")[0]
        self.assertEqual(" ".join(condition.split()),
                         f"github.ref != 'refs/heads/rewrite/rust' && !{FLAG} && "
                         "!(github.event_name == 'pull_request' && github.head_ref == 'rewrite/rust' && "
                         "github.event.pull_request.head.repo.full_name == github.repository)")

    def test_explicit_dispatch_selects_only_the_native_rewrite_editor(self):
        self.assertEqual(self.jobs["rw02-editor-arm64"].strip().splitlines(), [
            f"if: github.event_name == 'workflow_dispatch' && {FLAG} && {REWRITE}",
            "    uses: ./.github/workflows/rust-ubuntu-arm64-editor.yaml",
        ])
        self.assertEqual(self.editor.split("\non:\n")[1].split("\npermissions:")[0].strip(), "workflow_call:")
        self.assertEqual(re.findall(r"^    runs-on: (.+)$", self.editor, re.M), ["ubuntu-24.04-arm"])
        for backend in ("x11", "wayland"):
            self.assertIn(f"gui/native.py --backend {backend} --input --screen-reader", self.editor)
        self.assertIn('tools/rust-qa/ubuntu-reader/verify.py "$NATIVE_TARGET"', self.editor)
        self.assertIn('selection-reopen.json', self.editor)
        self.assertIn('artifacts/rust/gui-run/', self.editor)


if __name__ == "__main__":
    unittest.main()
