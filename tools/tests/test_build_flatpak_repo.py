from __future__ import annotations

import base64
import configparser
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).parents[1] / "build-flatpak-repo.py"
SPEC = importlib.util.spec_from_file_location("build_flatpak_repo", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RepositoryInputTests(unittest.TestCase):
    def test_rejects_unsafe_base_urls(self) -> None:
        for url in ("http://example.org", "https://user:password@example.org",
                    "https://example.org/?token=value", "https://example.org/#fragment",
                    "https://example.org/\nGPGKey=bad"):
            with self.subTest(url=url), self.assertRaises(MODULE.RepositoryError):
                MODULE.validate_url(url)

    def test_rejects_missing_mixed_duplicate_and_unexpected_bundles(self) -> None:
        cases = (
            ["immich-folder-watch-1.0.0-linux-x64.flatpak"],
            ["immich-folder-watch-1.0.0-linux-x64.flatpak", "immich-folder-watch-2.0.0-linux-arm64.flatpak"],
            ["immich-folder-watch-1.0.0-linux-x64.flatpak", "immich-folder-watch-2.0.0-linux-x64.flatpak"],
            ["immich-folder-watch-1.0.0-linux-x64.flatpak", "unexpected.flatpak"],
        )
        for filenames in cases:
            with self.subTest(filenames=filenames), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                for name in filenames:
                    (directory / name).touch()
                with self.assertRaises(MODULE.RepositoryError):
                    MODULE.find_bundles(directory)

    def test_descriptors_share_key_and_select_native_architecture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            MODULE.write_site_metadata(site, "https://example.org/app", b"public key", "master", "1.2.3")
            ref = configparser.ConfigParser()
            ref.read(site / f"{MODULE.APP_ID}.flatpakref")
            repo = configparser.ConfigParser()
            repo.read(site / "immich-folder-watch.flatpakrepo")
            self.assertEqual(ref["Flatpak Ref"]["GPGKey"], repo["Flatpak Repo"]["GPGKey"])
            self.assertEqual(base64.b64decode(ref["Flatpak Ref"]["GPGKey"]), b"public key")
            self.assertNotIn("Arch", ref["Flatpak Ref"])
            self.assertEqual(ref["Flatpak Ref"]["SuggestRemoteName"], "immich-folder-watch")
            self.assertEqual(ref["Flatpak Ref"]["Branch"], "master")
            self.assertEqual(ref["Flatpak Ref"]["RuntimeRepo"], "https://flathub.org/repo/flathub.flatpakrepo")


@unittest.skipUnless(all(shutil.which(tool) for tool in ("flatpak", "ostree", "gpg")),
                     "Flatpak, OSTree and GPG are required for repository integration tests")
class SignedRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="ifw-repo-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.keyring = cls.root / "gnupg"
        cls.keyring.mkdir(mode=0o700)
        cls.environment = patch.dict(os.environ, {
            "GNUPGHOME": str(cls.keyring), "TMPDIR": str(cls.root), "LC_ALL": "C",
            "XDG_DATA_HOME": str(cls.root / "data"), "XDG_CONFIG_HOME": str(cls.root / "config"),
            "XDG_CACHE_HOME": str(cls.root / "cache"), "FLATPAK_USER_DIR": str(cls.root / "user-flatpak"),
        })
        cls.environment.start()
        cls.addClassCleanup(cls.environment.stop)
        cls.addClassCleanup(subprocess.run, ["gpgconf", "--kill", "gpg-agent"],
                            check=False, capture_output=True)
        cls.run_command("gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", "",
                        "--quick-generate-key", "Flatpak repository test <test@example.invalid>",
                        "rsa2048", "sign", "0")
        listing = cls.run_command("gpg", "--batch", "--with-colons", "--list-secret-keys")
        cls.fingerprint = next(line.split(":")[9] for line in listing.splitlines() if line.startswith("fpr:"))

    @staticmethod
    def run_command(*arguments: str) -> str:
        result = subprocess.run(arguments, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(f"Command failed: {arguments}\n{result.stdout}\n{result.stderr}")
        return result.stdout

    def make_bundles(self, directory: Path, version: str, branch: str = "master") -> Path:
        bundles = directory / "bundles"
        bundles.mkdir(parents=True)
        source = directory / "source"
        self.run_command("ostree", "init", f"--repo={source}", "--mode=archive")
        for asset_arch, arch in MODULE.ARCHITECTURES.items():
            tree = directory / arch
            (tree / "files").mkdir(parents=True)
            (tree / "export").mkdir()
            metadata = (f"[Application]\nname={MODULE.APP_ID}\n"
                        f"runtime=org.freedesktop.Platform/{arch}/26.08\n"
                        f"sdk=org.freedesktop.Sdk/{arch}/26.08\ncommand=test\n")
            (tree / "metadata").write_text(metadata)
            (tree / "files" / "fixture").write_text(version)
            ref = f"app/{MODULE.APP_ID}/{arch}/{branch}"
            self.run_command("ostree", "commit", f"--repo={source}", f"--branch={ref}",
                             f"--add-metadata-string=xa.metadata={metadata}",
                             f"--add-metadata-string=xa.ref={ref}", "--generate-sizes", str(tree))
            self.run_command("flatpak", "build-bundle", f"--arch={arch}", str(source),
                             str(bundles / f"immich-folder-watch-{version}-{asset_arch}.flatpak"),
                             MODULE.APP_ID, branch)
        return bundles

    def test_signed_multiarch_repository_supports_updates_without_history(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            root = Path(temporary)
            site = root / "site"
            bundles = self.make_bundles(root / "one", "1.0.0")
            MODULE.build_repository(bundles, site, "https://example.org/app", self.fingerprint)
            client = root / "client"
            self.run_command("ostree", "init", f"--repo={client}", "--mode=archive")
            self.run_command("ostree", "remote", "add", f"--repo={client}",
                             "--set=gpg-verify-summary=true", "fixture", (site / "repo").as_uri())
            self.run_command("ostree", "remote", "gpg-import", f"--repo={client}",
                             f"--keyring={site / 'public-key.gpg'}", "fixture")
            refs = [f"app/{MODULE.APP_ID}/{arch}/master" for arch in MODULE.ARCHITECTURES.values()]
            self.run_command("ostree", "pull", f"--repo={client}", "fixture", *refs)
            first = self.run_command("ostree", "rev-parse", f"--repo={client}", f"fixture:{refs[0]}")
            # Replace the entire server repo, retaining no previous commit history.
            site.rename(root / "old-site")
            bundles = self.make_bundles(root / "two", "1.0.1")
            MODULE.build_repository(bundles, site, "https://example.org/app", self.fingerprint)
            self.run_command("ostree", "pull", f"--repo={client}", "fixture", *refs)
            second = self.run_command("ostree", "rev-parse", f"--repo={client}", f"fixture:{refs[0]}")
            self.assertNotEqual(first, second)
            self.assertTrue((site / "repo" / "summary.sig").is_file())
            # A fresh client must reject unsigned repository metadata.
            (site / "repo" / "summary.sig").unlink()
            result = subprocess.run(["ostree", "pull", f"--repo={client}", "fixture", *refs],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_flatpak_client_accepts_flatpakref_and_both_architectures(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            root = Path(temporary)
            bundles = self.make_bundles(root, "1.0.0")
            site = root / "site"
            MODULE.build_repository(bundles, site, "https://example.org/app", self.fingerprint)
            # Substitute only the transport URL for an entirely offline client check.
            MODULE.write_site_metadata(site, site.as_uri(), (site / "public-key.gpg").read_bytes(),
                                       "master", "1.0.0")
            self.run_command("flatpak", "install", "--user", "--noninteractive", "--no-deps",
                             "--no-related", "--no-deploy", str(site / f"{MODULE.APP_ID}.flatpakref"))
            for arch in MODULE.ARCHITECTURES.values():
                result = self.run_command("flatpak", "remote-info", "--user", f"--arch={arch}",
                                          "--show-ref", "immich-folder-watch", MODULE.APP_ID)
                self.assertEqual(result.strip(), f"app/{MODULE.APP_ID}/{arch}/master")

    def test_wrong_branch_is_rejected_without_publishing_partial_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            root = Path(temporary)
            bundles = self.make_bundles(root, "1.0.0", "test")
            with self.assertRaisesRegex(MODULE.RepositoryError, "Unexpected imported refs"):
                MODULE.build_repository(bundles, root / "site", "https://example.org", self.fingerprint)
            self.assertFalse((root / "site").exists())

    def test_site_size_limit_fails_without_publishing_partial_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            root = Path(temporary)
            bundles = self.make_bundles(root, "1.0.0")
            with patch.object(MODULE, "MAX_SITE_BYTES", 1), self.assertRaisesRegex(MODULE.RepositoryError, "Pages safety limit"):
                MODULE.build_repository(bundles, root / "site", "https://example.org", self.fingerprint)
            self.assertFalse((root / "site").exists())


if __name__ == "__main__":
    unittest.main()
