"""Resolve synthetic path-only Cargo workspaces to exercise real renames, features and target filters."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from check import ROOT, ROLES, cargo_output, inspect, violation


class WorkspaceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.workspace = self.area / "workspace"
        self.workspace.mkdir()
        (self.workspace / "Cargo.toml").write_text('[workspace]\nmembers=["members/*"]\nresolver="3"\n')
        suffix = ".exe" if os.name == "nt" else ""
        self.cargo = ROOT / "artifacts/rust/toolchain/bin" / ("cargo" + suffix)
        self.env = dict(os.environ, CARGO_HOME=str(self.area / "cargo-home"),
                        RUSTC=str(self.cargo.with_name("rustc" + suffix)), CARGO_NET_OFFLINE="true")
        for name in ROLES:
            self.crate(name, member=True)

    def crate(self, name, dependencies="", member=False, build=False):
        path = self.workspace / "members" / name if member else self.area / name
        (path / "src").mkdir(parents=True, exist_ok=True)
        (path / "src/lib.rs").write_text("", encoding="utf-8")
        (path / "Cargo.toml").write_text(
            f'[package]\nname="{name}"\nversion="0.1.0"\nedition="2024"\n' + dependencies, encoding="utf-8")
        if build:
            (path / "build.rs").write_text("fn main() {}\n", encoding="utf-8")

    def resolve(self, target="x86_64-unknown-linux-gnu"):
        cargo_output(self.cargo, self.workspace, self.env, "generate-lockfile", "--offline")
        return inspect(self.workspace, target, self.cargo, self.env)[:2]

    def test_renamed_transitive_product_build_dependency_only_on_its_target(self):
        self.crate("safe-fs", """[target.'cfg(windows)'.dependencies]
shim={package="bridge",path="../../../bridge"}
""", member=True)
        self.crate("bridge", """[build-dependencies]
codec={package="ifw-legacy",path="../workspace/members/ifw-legacy"}
""", build=True)
        _, linux_errors = self.resolve()
        self.assertEqual(linux_errors, [])
        profiles, windows_errors = self.resolve("aarch64-pc-windows-msvc")
        self.assertEqual(windows_errors, [
            "safe-fs -> bridge -> ifw-legacy: generic crates must be independent of the product"])
        edges = profiles["safe-fs"]["edges"]
        self.assertEqual({(alias, kind, condition) for _, _, kind, declarations in edges
                          for alias, condition in declarations},
                         {("shim", "normal", "cfg(windows)"), ("codec", "build", "")})

    def test_development_only_feature_unification_does_not_create_a_renderer_edge(self):
        self.crate("egui")
        self.crate("bridge", '[features]\nrender=["dep:paint"]\n[dependencies]\npaint={package="egui",path="../egui",optional=true}\n')
        self.crate("dev-gui", '[dependencies]\nbridge={path="../bridge",features=["render"]}\n')
        deps = ('[dependencies]\nbridge={path="../../../bridge"}\n'
                '[dev-dependencies]\ndev-gui={path="../../../dev-gui"}\n')
        self.crate("desktop-lifecycle", deps, member=True)
        profiles, errors = self.resolve()
        self.assertEqual(errors, [])
        self.assertEqual(len(profiles["desktop-lifecycle"]["edges"]), 1)
        self.crate("desktop-lifecycle", deps.replace('bridge={path="../../../bridge"}',
                                                    'bridge={path="../../../bridge",features=["render"]}'), member=True)
        profiles, errors = self.resolve()
        self.assertEqual(errors, ["desktop-lifecycle -> bridge -> egui: renderer or GUI inspection belongs in presentation"])
        self.assertTrue(any(row[2:] == ["normal", [("paint", "")]] for row in profiles["desktop-lifecycle"]["edges"]))

    def test_native_and_transport_adapters_can_use_their_backends(self):
        self.crate("zbus")
        self.crate("reqwest")
        self.crate("rusqlite")
        for member, backend in (("desktop-platform-log", "zbus"), ("ifw-immich", "reqwest"), ("ifw-legacy", "rusqlite")):
            self.crate(member, f'[dependencies]\n{backend}={{path="../../../{backend}"}}\n', member=True)
        profiles, errors = self.resolve()
        self.assertEqual(errors, [])
        self.assertEqual(len(profiles["desktop-platform-log"]["edges"]), 1)
        self.crate("desktop-lifecycle", '[dependencies]\nlogging={package="desktop-platform-log",path="../desktop-platform-log"}',
                   member=True)
        _, errors = self.resolve()
        self.assertTrue(any("desktop-lifecycle -> desktop-platform-log:" in issue for issue in errors))
        self.assertTrue(any("desktop-lifecycle -> desktop-platform-log -> zbus:" in issue for issue in errors))

    def test_a_sibling_members_release_feature_changes_the_shared_subtree(self):
        self.crate("reqwest")
        self.crate("bridge", '[features]\nclient=["dep:reqwest"]\n[dependencies]\nreqwest={path="../reqwest",optional=true}\n')
        for name, options in (("desktop-lifecycle", ""), ("ifw-immich", ',features=["client"]')):
            self.crate(name, '[dependencies]\nbridge={path="../../../bridge"' + options + '}\n', member=True)
        profiles, errors = self.resolve()
        self.assertTrue(any("desktop-lifecycle -> bridge -> reqwest:" in issue for issue in errors))
        for name in ("desktop-lifecycle", "ifw-immich"):
            self.assertTrue(any(row[3] == [("reqwest", "")] for row in profiles[name]["edges"]))

    def test_shared_identity_keeps_only_the_observed_dependency_kind(self):
        self.crate("backend")
        self.crate("safe-fs", """[dependencies]
backend={path="../../../backend"}
[target.'cfg(windows)'.build-dependencies]
backend={path="../../../backend"}
""", member=True, build=True)
        target = "aarch64-pc-windows-msvc" if os.name == "nt" else "x86_64-unknown-linux-gnu"
        profiles, errors = self.resolve(target)
        self.assertEqual(errors, [])
        kinds = {row[2] for row in profiles["safe-fs"]["edges"]}
        self.assertEqual(kinds, {"normal", "build"} if os.name == "nt" else {"normal"})

    def test_inspection_and_concrete_io_in_the_pure_policy_are_identified_by_package_name(self):
        for member in ROLES:
            self.assertIsNotNone(violation(member, "egui_inspection"))
        for package in ("windows-sys", "libdbus-sys", "reqwest", "rusqlite"):
            self.assertIsNotNone(violation("desktop-lifecycle", package))

    def test_new_member_requires_an_architectural_role(self):
        self.crate("new-engine", member=True)
        with self.assertRaisesRegex(ValueError, "Assign an architectural role.*new-engine"):
            self.resolve()

    def test_failed_native_check_replaces_a_stale_success_receipt(self):
        output = self.area / "result.json"
        output.write_text('{"status":"passed","profiles":{"old":{}}}', encoding="utf-8")
        other = "x86_64-unknown-linux-gnu" if os.name == "nt" else "x86_64-pc-windows-msvc"
        script = Path(__file__).with_name("check.py")
        run = subprocess.run([sys.executable, "-B", str(script), other, "--output", str(output)],
                             capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 1)
        result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual((result["status"], result["target"]), ("failed", other))
        self.assertTrue(result["error"])
        self.assertNotIn("profiles", result)


if __name__ == "__main__":
    unittest.main()
