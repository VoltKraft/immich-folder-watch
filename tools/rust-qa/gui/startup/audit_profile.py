"""Bind the optional full GUI source audit to the qualified startup-language projection."""
import json
from pathlib import Path

from gui import source_profile
from gui.startup import vendor as registry
from sources import yaml_prepare

QA = Path(__file__).resolve().parents[2]
ROOT = QA.parents[1]
BASE = "c63d91c42eae9f71f07a2d1816214a1e16609ef8"
UPDATED = "bb3afd5bb27becb6ab1143861196acc004b9556a"
UPDATED_YAML = "7c317d1ec009960a6ec7c279539c5380358de956b9846fde7a18ddc0b579f450"
LOCK = "bdda6dc843f34b90bbe9efd99c84e994fd293a5d6ad88c52f6c70ceb8ea97679"
ORDINARY_LOCK = "6716b1cc5835c1fbec9c9485773bdacfd63c4f5d01568a9aa94a8839c2e81d25"
ORDINARY_GUI = ("tools/rust-qa/gui", "aa1d480aebc839c4c5a742be3a547af19273739bcd6634c36afd556a353139ed",
                "04a43e887aa4440b29a87b9d36e545e51dbc39f36c388a4bc24b3544ba2d6205")
ORDINARY_LINUX_FEATURES = (235, "657eb6625ab78dad9cc9c2da0fe9714c880dd2b4b61345f540ac358def514ce0")
# Release compiler source snapshots in the reviewed native.json from 75283a3.
LOCAL = {
    "native-gui-assessment": ("tools/rust-qa/gui", "40293313b276c9023e69b75741d356af9388c29f80566a892a2e08c0201d85fb",
                              "1f7bcd022421c81b9d074d918228f815fb1831eb15d8b92e51b1b2f8b5899695"),
    "ifw-yaml-assessment": ("tools/rust-qa/yaml", "a0830ccfcda0b3dce7311d064ea132450c6b11d43e6fada9ef0a35e7b5153ded",
                            "a60c8d554bc5003ac48337aa74e8081e80322579d50b83b44fe374321866afd6"),
    "desktop-lifecycle": ("rust/crates/desktop-lifecycle", "b36dd12119a0d6894f15ffb44d552c077332ece9d996487fdab879e73eb72396",
                          "ff14b64e27115cf5643862ac492dbd6a8e9d25e578404aa7d5564b13b6bcc09c"),
}
FEATURES = {
    "x86_64-unknown-linux-gnu": (251, "ffba14418cefd6534b37a6ca7a5fb3dbdd5c4cd873074c59cf4d9cd50dbd15f2"),
    "aarch64-unknown-linux-gnu": (250, "c428080cb3223c510832051d449526a6f6b125324d9b51a4337cb5f0fdac3201"),
    "x86_64-pc-windows-msvc": (135, "b32b53dc0616ce7d73e664dcdc5eb19f6ade2f1c6c6d8a96a4ef5e7b9e49a3e1"),
    "aarch64-pc-windows-msvc": (135, "d4257db8af496165dd32d43172d7d39142a5108fbccbab9a3105f8cf855d313b"),
}


class StartupAudit:
    @classmethod
    def for_canonical(cls, manifest, vendor, target):
        """Require this checkout's composed manifest and the reviewed current YAML library."""
        return cls(manifest, vendor, target, canonical=True)

    def __init__(self, manifest, vendor, target, *, canonical=False):
        self.gui = manifest.parent
        self.project = self.gui.parents[2]
        self.vendor = vendor.resolve(strict=True)
        valid_root = self.project == ROOT if canonical else (
            self.project.name == "project" and self.project.is_relative_to(ROOT / "artifacts/rust"))
        if (target not in FEATURES or manifest != self.project / "tools/rust-qa/gui/Cargo.toml"
                or self.project.resolve() != self.project or not valid_root):
            raise ValueError("Expected the selected canonical GUI or an isolated staged project")
        lock = source_profile.sha(self.gui / "Cargo.lock")
        allowed = LOCAL.copy()
        count, digest = FEATURES[target]
        self.yaml_revision = BASE
        if lock == ORDINARY_LOCK and not canonical:
            allowed.pop("ifw-yaml-assessment")
            allowed["native-gui-assessment"] = ORDINARY_GUI
            if "linux" in target:
                count, digest = ORDINARY_LINUX_FEATURES
        elif lock == LOCK:
            path, manifest_sha, _ = LOCAL["ifw-yaml-assessment"]
            actual = source_profile.tree_info(self.project / path / "src")["sha256"]
            if actual == UPDATED_YAML:
                self.yaml_revision = UPDATED
                allowed["ifw-yaml-assessment"] = (path, manifest_sha, actual)
            elif canonical:
                raise ValueError("The canonical GUI requires the reviewed current YAML sources")
        else:
            raise ValueError("The GUI lock differs from the reviewed source profile")
        self.local_sources = allowed
        if self.vendor.parts[-3:] != ("registry", "src", "reviewed"):
            raise ValueError("Use the reviewed startup registry directory")
        inventory = self.vendor.parents[2] / "registry-sources.json"
        receipt = registry.CORRECTED_RECEIPT_SHA256 if canonical else registry.RECEIPT_SHA256
        if source_profile.sha(inventory) != receipt:
            raise ValueError("The compiler source inventory differs from the selected GUI profile")
        self.registry = json.loads(inventory.read_bytes())
        self.source_roots = {}
        for name, (path, manifest_sha, source_sha) in allowed.items():
            root = self.project / path
            if (root.resolve() != root or (root / "Cargo.toml").is_symlink()
                    or source_profile.sha(root / "Cargo.toml") != manifest_sha
                    or source_profile.tree_info(root / "src")["sha256"] != source_sha
                    or (root / "build.rs").exists()):
                raise ValueError(f"The staged first-party sources differ for {name}")
            self.source_roots[name] = root
        self.features = {"packages": count, "nativeFeatureSetsSha256": digest}

    def local(self, package):
        name = package["name"]
        root = self.source_roots.get(name)
        if (root is None or package["version"] != "0.0.0"
                or Path(package["manifest_path"]).resolve() != root / "Cargo.toml"):
            raise ValueError(f"Unexpected first-party dependency {name}")
        if name == "native-gui-assessment":
            return {"assessmentWorkspaceMember": True}
        path, manifest_sha, source_sha = self.local_sources[name]
        row = {"repositoryManifest": path + "/Cargo.toml"}
        if name == "ifw-yaml-assessment":
            libraries = [(t["name"], Path(t["src_path"]).resolve()) for t in package["targets"] if t["kind"] == ["lib"]]
            if libraries != [("ifw_yaml_assessment", root / "src/lib.rs")]:
                raise ValueError("Cargo did not select the reviewed YAML library")
            row["firstPartyLibrary"] = {"revision": self.yaml_revision, "manifestSha256": manifest_sha,
                                        "sourcesSha256": source_sha, "entry": "src/lib.rs"}
        return row

    def filtered(self, package, checksum):
        key = package["name"] + "-" + package["version"]
        root = self.vendor / key
        expected = self.registry.get(key)
        if (not expected or checksum != expected["originalSha256"]
                or package["source"] != "registry+https://github.com/rust-lang/crates.io-index"
                or Path(package["manifest_path"]).resolve() != root / "Cargo.toml"):
            raise ValueError(f"Unexpected directory source for {key}")
        if not expected["transformations"]:
            return None
        archive = self.vendor.parents[1] / "cache/reviewed" / (key + ".crate")
        if key == "base64-0.23.1":
            files, changes = yaml_prepare.source_files(archive, key, checksum)
        elif key == "accesskit_unix-0.24.1":
            from sources import accesskit_source
            files, changes = accesskit_source.registry_files(archive, checksum)
        else:
            raise ValueError(f"Unreviewed transformed package {key}")
        hashes = {name: yaml_prepare.digest(data) for name, data in files.items()}
        tree = yaml_prepare.digest(yaml_prepare.canonical(hashes))
        if (tree != expected["compilerTreeSha256"] or changes != expected["transformations"]
                or len(hashes) != expected["files"]):
            raise ValueError(f"The reconstructed {key} source differs from its review")
        actual = {}
        for item in root.rglob("*"):
            if item.is_symlink():
                raise ValueError(f"Unexpected linked compiler input for {key}")
            if item != root / ".cargo-checksum.json" and not item.is_dir():
                if not item.is_file():
                    raise ValueError(f"Unexpected compiler input for {key}")
                actual[item.relative_to(root).as_posix()] = source_profile.sha(item)
        if (actual != hashes or json.loads((root / ".cargo-checksum.json").read_bytes())
                != {"files": hashes, "package": checksum}):
            raise ValueError(f"The supplied {key} files differ from the reviewed compiler source")
        return {"compilerTreeSha256": tree, "files": len(hashes), "transformations": changes}
