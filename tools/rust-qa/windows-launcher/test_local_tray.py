"""Check portable compiler-path readback before running a local Explorer trial."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import local_tray


class LocalTrayTests(unittest.TestCase):
    def receipt(self):
        base = "D:/build/retained"
        gui = base + "/project/tools/rust-qa/gui"
        messages = [dict(reason="compiler-artifact", executable=base + "/build/release/" + local_tray.GUI,
                         manifest_path=gui + "/Cargo.toml", target=dict(name="native-gui-assessment",
                                                                      kind=["bin"], src_path=gui + "/src/main.rs"))]
        record = {}
        for crate in ("eframe", "winit"):
            package = "artifacts/retained/" + crate
            manifest = package + "/Cargo.toml"
            source = package + "/src/lib.rs"
            outputs = {"release/deps/lib" + crate + "-abc" + ext: "digest" for ext in (".rlib", ".rmeta")}
            record[crate + "Unit"] = dict(manifest=manifest, crateRoot=source, features=["default"], outputs=outputs)
            messages.append(dict(reason="compiler-artifact", target=dict(name=crate, kind=["lib"], src_path=gui + "/" + source),
                                 manifest_path=gui + "/" + manifest, features=["default"],
                                 filenames=[base + "/build/" + path for path in outputs]))
        messages.append(dict(reason="build-finished", success=True))
        return messages, record

    def test_replayed_libraries_must_belong_to_the_original_compiler_tree(self):
        messages, record = self.receipt()
        def stream():
            return "\n".join(json.dumps(m) for m in messages).encode()
        local_tray.check_compiler(stream(), record)
        messages[1]["filenames"][0] = "D:/other/build/release/deps/libeframe-abc.rlib"
        with self.assertRaises(ValueError):
            local_tray.check_compiler(stream(), record)

    def test_rejects_wrong_actions_digest_before_opening_the_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "original.zip"
            path.write_bytes(b"unopened")
            with self.assertRaisesRegex(ValueError, "Actions SHA-256"):
                local_tray.stage(path, hashlib.sha256(b"different").hexdigest(), Path(temporary))
