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

    def test_plasma_menu_and_watcher_have_both_native_linux_runners(self):
        filename = "rust-linux-plasma.yaml"
        self.check_rust_workflow(filename, {"actions/checkout", "actions/upload-artifact"})
        source = (WORKFLOWS / filename).read_text()
        self.assertEqual(set(re.findall(r"- runner: (\S+)\s+target: (\S+)", source)), {
            ("ubuntu-24.04", "x86_64-unknown-linux-gnu"),
            ("ubuntu-24.04-arm", "aarch64-unknown-linux-gnu"),
        })
        desktop = (WORKFLOWS / "rust-desktop-assessment.yaml").read_text()
        for observer in ("tools/rust-qa/linux-services/gui_watcher.py", "--restart-watcher",
                         'flatpak/run.py plasma-native --hosted-runtime "$PLATFORM_DEPLOYMENT" --tray-menu'):
            self.assertIn(observer, source)
            self.assertNotIn(observer, desktop)
        self.assertIn('tools/RustCompatibilityOracle/installed/launch/graphics.py "$PLATFORM_DEPLOYMENT"', source)
        self.assertIn("artifacts/rust/flatpak-gui-launch-assessment/", source)

    def test_native_linux_worker_budget_reuses_the_two_desktop_measurements(self):
        name = "rust-linux-worker-budget.yaml"
        self.check_rust_workflow(name, {"actions/checkout", "actions/setup-dotnet", "actions/upload-artifact"})
        source = (WORKFLOWS / name).read_text()
        self.assertEqual(re.findall(r"^      - '(.*)'$", source.split("permissions:", 1)[0], re.M), [".github/workflows/" + name])
        self.assertIn("  workflow_dispatch:", source)
        self.assertNotIn("pull_request", source)
        self.assertEqual(set(re.findall(r"- runner: (\S+)\s+target: (\S+)", source)), {
            ("ubuntu-24.04", "x86_64-unknown-linux-gnu"), ("ubuntu-24.04-arm", "aarch64-unknown-linux-gnu")})
        self.assertIn("  actions: read", source)
        broad = (WORKFLOWS / "rust-desktop-assessment.yaml").read_text()
        for phase in ("reference", "candidate"):
            command = "bash tools/rust-qa/performance/hosted_budget.sh " + phase
            self.assertIn(command, source)
            self.assertIn(command, broad)

    def test_focused_windows_workflows_are_branch_bound_and_cannot_publish(self):
        for name in ("rust-windows-msi-interop.yaml", "rust-windows-installed-upload.yaml"):
            with self.subTest(workflow=name):
                self.check_rust_workflow(name, {"actions/checkout", "actions/setup-dotnet", "actions/upload-artifact"})
        for name in ("rust-windows-x64-build.yaml", "rust-windows-x64-gui-build.yaml",
                     "rust-windows-x64-combined-build.yaml", "rust-windows-x64-tray-build.yaml",
                     "rust-windows-arm64-notification.yaml", "rust-windows-arm64-display.yaml"):
            self.check_rust_workflow(name, {"actions/checkout", "actions/upload-artifact"})

    def test_arm64_display_keeps_both_attempts_and_the_native_builds(self):
        source = (WORKFLOWS / "rust-windows-arm64-display.yaml").read_text()
        self.assertEqual(re.findall(r"runs-on: (\S+)", source), ["windows-11-arm"])
        self.assertIn("NATIVE_TARGET: aarch64-pc-windows-msvc", source)
        default, job = source.split("\njobs:\n", 1)
        self.assertNotIn("actions: read", default)
        self.assertIn("    permissions:\n      contents: read\n      actions: read\n", job)
        steps = dict(step.split("\n", 1) for step in job.split("      - name: ")[1:])
        canonical = steps["Observe the canonical source-monitor edit"]
        retained = steps["Observe the retained source-monitor edit"]
        private = steps["Measure the canonical source frame on a private input desktop"]
        private_retained = steps["Measure the retained source frame on a private input desktop"]
        selection = steps["Select the current or requested original ARM64 selection subject"]
        reopened = steps["Reopen the selected filename in the original ARM64 primary"]
        archive = steps["Retain both measurements and the original compiler outputs"]
        self.assertIn("windows-display/run.py $env:NATIVE_TARGET --require source-frame", canonical)
        self.assertIn("windows-display/run.py $env:NATIVE_TARGET --retained --require source-frame", retained)
        self.assertIn("windows-display/private_source.py\n", private)
        self.assertIn("windows-display/private_source.py --retained", private_retained)
        for step in (canonical, retained, private, private_retained, selection, archive):
            self.assertIn("!cancelled() && steps.inputs.outcome == 'success'", step)
        self.assertIn("windows-display/selection_archive.py $id", selection)
        self.assertIn("GH_TOKEN: ${{ github.token }}", selection)
        self.assertEqual(job.count("GH_TOKEN:"), 1)
        self.assertIn("!cancelled() && steps.selection.outcome == 'success'", reopened)
        self.assertIn("windows-display/private_selection.py --archive", reopened)
        self.assertIn("windows-display/private_selection.py\n", reopened)
        self.assertIn("windows-display/archive_pair.py", steps["Compile both native GUI subjects and archive the corresponding worker"])
        self.assertIn("windows-display/venue.py", steps["Read the existing Remote Desktop settings and aggregate WTS session states"])
        for path in ("windows-display-inputs/", "windows-display-runs/", "windows-display-retained-runs/",
                     "windows-display-private/", "windows-display-retained-private/", "windows-display-venue/",
                     "windows-selection-private/"):
            self.assertIn(path, archive)

    def test_rewrite_windows_x64_has_only_compiler_inputs_on_actions(self):
        compiler = "rust-windows-x64-build.yaml"
        gui_compiler = "rust-windows-x64-gui-build.yaml"
        combined_compiler = "rust-windows-x64-combined-build.yaml"
        tray_compiler = "rust-windows-x64-tray-build.yaml"
        for path in WORKFLOWS.glob("rust-*.yaml"):
            source = path.read_text()
            # Look at runner selections, including inline matrix rows.
            windows = re.findall(r"(?:runs-on|runner|os):\s*['\"]?(windows-[\w.-]+)", source)
            allowed = {"windows-2025"} if path.name in (
                compiler, gui_compiler, combined_compiler, tray_compiler) else {"windows-11-arm"}
            self.assertLessEqual(set(windows), allowed, path.name)
        source = (WORKFLOWS / compiler).read_text()
        commands = re.findall(r"^          python -B (.+)$", source, re.M)
        self.assertEqual(commands, [
            "tools/rust-qa/instance/cross-session/build_msi_endpoint.py $env:NATIVE_TARGET",
            "tools/rust-qa/windows-local/workspace.py build artifacts/rust/local-vm-inputs/workspace",
            "tools/rust-qa/realtime/run.py $env:NATIVE_TARGET --build-only --output artifacts/rust/local-vm-inputs/realtime",
        ])
        gui = (WORKFLOWS / gui_compiler).read_text()
        self.assertEqual(re.findall(r"^          python -B (.+)$", gui, re.M), [
            "tools/rust-qa/build-gui-probe.py $env:NATIVE_TARGET --local-x64-inputs artifacts/rust/local-vm-inputs/gui",
        ])
        combined = (WORKFLOWS / combined_compiler).read_text()
        self.assertEqual(re.findall(r"^          python -B (.+)$", combined, re.M), [
            "tools/rust-qa/combined-profile/run.py --x64-vm-inputs --fetch "
            "--output artifacts/rust/combined-profile/runs/local-x64-inputs",
        ])
        tray = (WORKFLOWS / tray_compiler).read_text()
        self.assertEqual(re.findall(r"^          python -B (.+)$", tray, re.M), [
            "tools/rust-qa/windows-launcher/local_build.py $env:NATIVE_TARGET",
        ])
        ci = (WORKFLOWS / "ci.yaml").read_text().split("  build-windows:\n", 1)[1].split("    steps:", 1)[0]
        self.assertIn("github.ref != 'refs/heads/rewrite/rust'", ci)
        self.assertIn("github.head_ref == 'rewrite/rust'", ci)
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", ci)
        for name in ("rust-compatibility", "rust-feasibility", "rust-realtime", "rust-desktop-assessment", "rust-legacy-install"):
            with self.subTest(workflow=name):
                runners = re.findall(r"runner: ([\w.-]+)", (WORKFLOWS / (name + ".yaml")).read_text())
                self.assertCountEqual(runners, ["ubuntu-24.04", "ubuntu-24.04-arm", "windows-11-arm"])
        activation = (WORKFLOWS / "rust-windows-msi-interop.yaml").read_text()
        self.assertIn("        arch: [arm64]\n        primary: [Rust, WPF]", activation)
        self.assertIn("arch: arm64-private-input, sdkArch: arm64, primary: WPF", activation)

    def test_native_linux_notification_workflow_is_branch_bound_and_cannot_publish(self):
        self.check_rust_workflow("rust-linux-notification.yaml", {"actions/checkout", "actions/upload-artifact"})

    def test_native_notices_use_the_hash_of_the_uploaded_receipt(self):
        source = (WORKFLOWS / "rust-desktop-assessment.yaml").read_text()
        stages = source.split("      - name: Retain the exact native compiler receipt ZIP\n", 1)[1]
        original, rest = stages.split("      - name: Assemble and read back the original notices", 1)
        assembly, rest = rest.split("      - name: Retain the verified native development notices", 1)
        published = rest.split("      - name:", 1)[0]
        self.assertIn("id: receipt_zip", original)
        self.assertIn("archive: false", original)
        self.assertIn("rust-native-input-${{ matrix.target }}-${{ github.sha }}.zip", original)
        self.assertIn("steps.receipt_zip.outputs.artifact-digest", assembly)
        self.assertEqual(assembly.count('--archive-sha256 "$digest"'), 2)
        self.assertIn("steps.notices.outcome == 'success'", published)
        self.assertIn("archive: false", published)

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
