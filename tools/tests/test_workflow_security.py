from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
PWSH = os.environ.get("IFW_TEST_PWSH") or shutil.which("pwsh")


def workflow_script(step_name: str) -> str:
    """Read the exact WinGet inline script, so tests exercise deployed source."""
    source = (WORKFLOWS / "winget.yaml").read_text()
    step = source.split(f"      - name: {step_name}\n", 1)[1]
    step = step.split("\n      - ", 1)[0]
    return "\n".join(line[10:] for line in step.split("        run: |\n", 1)[1].splitlines())


class WorkflowSecurityPolicyTests(unittest.TestCase):
    def test_external_actions_and_containers_are_immutable(self):
        for path in WORKFLOWS.glob("*.yaml"):
            for reference in re.findall(r"^\s*(?:- )?uses: (\S+)", path.read_text(), re.M):
                if not reference.startswith("./"):
                    with self.subTest(workflow=path.name, reference=reference):
                        self.assertRegex(reference, r"@[0-9a-f]{40}$")
            for image in re.findall(r"^\s*image: (\S+)", path.read_text(), re.M):
                self.assertRegex(image, r"@sha256:[0-9a-f]{64}$")

    def test_release_permissions_do_not_reach_build_jobs(self):
        source = (WORKFLOWS / "release.yaml").read_text()
        self.assertIn("\npermissions:\n  contents: read\n", source.split("\njobs:", 1)[0])
        jobs = dict(re.findall(r"^  ([\w-]+):\n(.*?)(?=^  [\w-]+:\n|\Z)", source.split("\njobs:\n", 1)[1], re.M | re.S))
        for name, job in jobs.items():
            scopes = re.findall(r"^      ([\w-]+): (read|write)$", job, re.M)
            allowed = {"contents": "write"} if name == "publish-release" else {"actions": "write"} if name.startswith("trigger-") else {}
            self.assertEqual(dict(scopes), allowed, name)
        for name in ("prepare-release", "build-windows", "build-flatpak", "publish-release"):
            self.assertIn("persist-credentials: false", jobs[name], name)

    def test_pages_smoke_uses_production_upload_pin_without_deployment_permissions(self):
        production = (WORKFLOWS / "flatpak-pages.yaml").read_text()
        smoke = (WORKFLOWS / "pages-artifact-validation.yaml").read_text()
        pattern = r"uses: actions/upload-pages-artifact@([0-9a-f]{40})"
        self.assertEqual(re.findall(pattern, smoke), re.findall(pattern, production))
        self.assertIn("\npermissions:\n  contents: read\n", smoke)
        self.assertNotRegex(smoke, r"(?m)^\s*[\w-]+: write\s*$")
        self.assertNotIn("secrets.", smoke)
        self.assertNotIn("environment:", smoke)
        self.assertNotIn("uses: actions/deploy-pages@", smoke)
        downloads = re.findall(r"uses: actions/download-artifact@([0-9a-f]{40})[^\n]*\n(.*?)(?=\n      -|\Z)", smoke, re.S)
        self.assertEqual(len(downloads), 2)
        self.assertEqual(downloads[0][0], downloads[1][0])
        for _, settings in downloads:
            self.assertIn("artifact-ids: ${{ steps.upload.outputs.artifact_id }}", settings)
        self.assertNotIn("continue-on-error: true", smoke.split("      - name: Retry the exact", 1)[1])

    def check_rust_workflow(self, filename, expected_actions):
        source = (WORKFLOWS / filename).read_text()
        self.assertIn("branches: [rewrite/rust]", source)
        self.assertIn("if: github.ref == 'refs/heads/rewrite/rust'", source)
        self.assertIn("\npermissions:\n  contents: read\n", source)
        self.assertNotRegex(source, r"(?m)^\s*[\w-]+: write\s*$")
        self.assertNotIn("secrets.", source)
        self.assertNotIn("secrets: inherit", source)
        self.assertNotIn("environment:", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("${{ github.sha }}", source)
        actions = re.findall(r"^\s*- uses: (\S+)|^\s*uses: (\S+)", source, re.M)
        self.assertEqual({(first or second).split("@", 1)[0] for first, second in actions}, expected_actions)
        # Release listens to the exact CI workflow name. Rust feasibility work
        # must remain outside that publication event chain even if it succeeds.
        name = re.search(r"^name: (.+)$", source, re.M).group(1)
        release = (WORKFLOWS / "release.yaml").read_text()
        trigger = release.split("\npermissions:", 1)[0]
        self.assertNotIn(name, trigger)
        self.assertNotRegex(source, r"(?i)gh\s+(release|workflow)|dispatches|deploy-pages|flatpak\s+build-update-repo")

    def test_rust_reference_is_branch_bound_and_cannot_publish(self):
        self.check_rust_workflow("rust-compatibility.yaml",
                                 {"actions/checkout", "actions/setup-dotnet", "actions/upload-artifact"})

    def test_rust_feasibility_is_branch_bound_and_cannot_publish(self):
        self.check_rust_workflow("rust-feasibility.yaml",
                                 {"actions/checkout", "actions/setup-dotnet", "actions/upload-artifact"})

    def test_rust_desktop_assessment_is_branch_bound_and_cannot_publish(self):
        self.check_rust_workflow("rust-desktop-assessment.yaml",
                                 {"actions/checkout", "actions/setup-dotnet", "actions/upload-artifact"})

    def test_native_compiler_download_record_is_identical_with_windows_newlines(self):
        script = (ROOT / "tools/rust-qa/install-toolchain.sh").read_text()
        selection = script.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        inputs = ROOT / "rust/toolchain-inputs.json"
        for target, spec in json.loads(inputs.read_text())["targets"].items():
            with self.subTest(target=target):
                code = "import sys\nsys.stdout.reconfigure(newline='\\r\\n')\n" + selection
                pair = subprocess.check_output([sys.executable, "-c", code, str(inputs), target])
                self.assertEqual(pair, f"{spec['rust']['url']} {spec['rust']['sha256']}\n".encode("ascii"))

    def test_winget_scripts_do_not_interpolate_expression_source(self):
        source = (WORKFLOWS / "winget.yaml").read_text()
        scripts = re.findall(r"^        run: \|\n((?:^          .*\n|^\n)*)", source, re.M)
        self.assertGreater(len(scripts), 5)
        for script in scripts:
            self.assertNotIn("${{", script)


class ReleaseCheckoutSecurityTests(unittest.TestCase):
    def setUp(self):
        source = (WORKFLOWS / "release.yaml").read_text()
        self.job = source.split("  build-flatpak:\n", 1)[1].split("\n  publish-release:", 1)[0]
        guard = self.job.split("      - name: Verify trusted release checkout\n", 1)[1]
        guard = guard.split("\n      - name:", 1)[0]
        self.script = "\n".join(
            line[10:] for line in guard.split("        run: |\n", 1)[1].splitlines()
        )

    def test_trusted_checkout_and_guard_precede_repository_execution(self):
        checkout = self.job.split("      - name: Checkout\n", 1)[1].split("\n      - name:", 1)[0]
        self.assertIn("ref: refs/heads/${{ github.event.repository.default_branch }}", checkout)
        self.assertNotIn("needs.prepare-release.outputs.target_sha", checkout)
        self.assertLess(self.job.index("- name: Verify trusted release checkout"),
                        self.job.index("- name: Read pinned Flatpak SDK"))
        self.assertIn('TARGET_SHA: ${{ needs.prepare-release.outputs.target_sha }}', self.job)
        self.assertIn('--commit "$TARGET_SHA"', self.job)
        self.assertNotIn("${{", self.script)

    def test_guard_accepts_only_exact_checked_out_commit_before_execution(self):
        # Windows also exposes a WSL bash launcher; use Git Bash for this native
        # temporary checkout, matching the shell used by Actions' bash steps.
        bash = shutil.which("bash")
        if os.name == "nt":
            git_path = Path(shutil.which("git") or "")
            bash = str(git_path.parent.parent / "bin" / "bash.exe")
        self.assertTrue(bash and Path(bash).is_file(), "A working Bash executable is required")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
            git("init", "--quiet")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "--quiet", "--allow-empty", "-m", "First")
            old = git("rev-parse", "HEAD")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "--quiet", "--allow-empty", "-m", "Second")
            current = git("rev-parse", "HEAD")
            env = {**os.environ, "GITHUB_WORKSPACE": root.as_posix(),
                   "GIT_TEST_ASSUME_DIFFERENT_OWNER": "1", "LC_ALL": "C",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
            ownership_check = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, env=env,
                capture_output=True, text=True, timeout=10,
            )
            self.assertNotEqual(ownership_check.returncode, 0)
            self.assertIn("dubious ownership", ownership_check.stderr)
            cases = [(current, True), (old, False), ("f" * 40, False),
                     ("", False), ("main", False), (current + "\n", False),
                     ("$(touch injected)", False), ("'; touch injected; #", False)]
            for target, allowed in cases:
                with self.subTest(target=target):
                    sentinel = root / "executed"
                    sentinel.unlink(missing_ok=True)
                    result = subprocess.run(
                        [str(bash), "-c", self.script + "\ntouch executed\n"],
                        cwd=root, env={**env, "TARGET_SHA": target},
                        capture_output=True, text=True, timeout=10,
                    )
                    self.assertEqual(result.returncode == 0, allowed, result.stdout + result.stderr)
                    self.assertEqual(sentinel.exists(), allowed)
                    self.assertFalse((root / "injected").exists())


@unittest.skipUnless(PWSH, "PowerShell is required; Windows CI runs these regression cases")
class WinGetPowerShellSecurityTests(unittest.TestCase):
    def run_script(self, script: str, env: dict[str, str] | None = None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script_path = root / "test.ps1"
            output = root / "github-output"
            script_path.write_text(script)
            result = subprocess.run(
                [str(PWSH), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script_path)],
                cwd=root,
                env={**os.environ, "GITHUB_OUTPUT": str(output), "XDG_CACHE_HOME": str(root / "cache"),
                     "XDG_CONFIG_HOME": str(root / "config"), "XDG_DATA_HOME": str(root / "data"), **(env or {})},
                capture_output=True, text=True, timeout=30,
            )
            return result, output.read_text() if output.exists() else "", (root / "injected").exists()

    def test_manual_release_uses_validated_tag_and_workflow_commit(self):
        result, output, _ = self.run_script(workflow_script("Determine checkout ref"), {
            "MANUAL_TAG": "v2.11.3", "EVENT_NAME": "workflow_dispatch", "WORKFLOW_SHA": "a" * 40,
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, f"target_ref={'a' * 40}\nrelease_tag=v2.11.3\n")

    def test_release_event_uses_validated_tag(self):
        result, output, _ = self.run_script(workflow_script("Determine checkout ref"), {
            "EVENT_RELEASE_TAG": "v2.11.3", "EVENT_NAME": "release", "MANUAL_TAG": "",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, "target_ref=v2.11.3\nrelease_tag=v2.11.3\n")

    def test_rejects_script_and_output_injection_before_checkout(self):
        for value in ['$(Set-Content injected yes)', 'v1.2.3\nrelease_tag=v9.9.9',
                      '"; Set-Content injected yes; #', 'v1.2.3-rc.1', 'v01.2.3', 'V1.2.3']:
            for field, event in [("MANUAL_TAG", "workflow_dispatch"), ("EVENT_RELEASE_TAG", "release")]:
                with self.subTest(value=value, field=field):
                    result, output, injected = self.run_script(workflow_script("Determine checkout ref"), {
                        "MANUAL_TAG": "", "EVENT_RELEASE_TAG": "", field: value,
                        "EVENT_NAME": event, "WORKFLOW_SHA": "a" * 40,
                    })
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(output, "")
                    self.assertFalse(injected)

    def test_download_hash_mismatch_stops_before_execution(self):
        script = '''
function Invoke-WebRequest { param($Uri, $OutFile) Set-Content $OutFile 'tampered executable' }
''' + workflow_script("Download and verify pinned wingetcreate") + '\nSet-Content injected yes\n'
        result, _, executed = self.run_script(script)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256 verification failed", result.stderr)
        self.assertFalse(executed)


if __name__ == "__main__":
    unittest.main()
