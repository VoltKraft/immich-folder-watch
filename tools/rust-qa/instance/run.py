"""Exercise actual old/new activation and independent native file locks between disposable processes."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Child:
    def __init__(self, command, cwd, env):
        self.proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
        self.events = queue.Queue()
        self.reader = threading.Thread(target=self.read_output, daemon=True)
        self.reader.start()

    def read_output(self):
        for line in self.proc.stdout:
            self.events.put(line.rstrip("\r\n"))
        self.events.put(None)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(timeout=15)
        self.reader.join(timeout=5)
        self.proc.stdin.close()
        self.proc.stdout.close()

    def expect(self, event):
        try:
            actual = self.events.get(timeout=35)
        except queue.Empty as err:
            raise TimeoutError(f"Waiting for {event} from fixture process {self.proc.pid}") from err
        if actual != event:
            raise RuntimeError(f"Expected {event}, received {actual!r} from fixture process {self.proc.pid}")

    def send(self, command):
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()

    def success(self):
        code = self.proc.wait(timeout=15)
        if code != 0:
            raise RuntimeError(f"Fixture process {self.proc.pid} exited {code}")


def build(args, build_dir, env):
    oracle = build_dir / "oracle"
    oracle.mkdir(parents=True)
    pins = json.loads((HERE / "legacy-inputs.json").read_text())
    sources = {HERE / name: oracle / name for name in ("Program.cs", "InstanceOracle.csproj")}
    for source, expected in pins["windows" if os.name == "nt" else "linux"].items():
        path = ROOT / source
        data = path.read_bytes()
        if os.name == "nt":
            data = data.replace(b"\r\n", b"\n")
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Legacy source changed since {pins['reference']}: {source}")
        (oracle / path.name).write_bytes(data)
    for path, destination in sources.items():
        shutil.copyfile(path, destination)
    config = oracle / "NuGet.Config"
    config.write_text("<configuration><packageSources><clear /></packageSources></configuration>\n")
    output = build_dir / "managed"
    dotnet = shutil.which("dotnet", path=env["PATH"])
    if not dotnet:
        raise FileNotFoundError("The pinned native .NET SDK is required")
    sdk = subprocess.check_output([dotnet, "--version"], cwd=ROOT, env=env, text=True).strip()
    if sdk != json.loads((ROOT / "global.json").read_text())["sdk"]["version"]:
        raise RuntimeError(f"Unexpected .NET SDK {sdk}")
    subprocess.run([dotnet, "build", "InstanceOracle.csproj", "-c", "Release", "-o", str(output),
                    "--configfile", str(config), "-p:UseSharedCompilation=false", "-nodeReuse:false",
                    "-p:ImportDirectoryBuildProps=false", "-p:ImportDirectoryBuildTargets=false",
                    "-p:UseAppHost=false", "--disable-build-servers", "--nologo"],
                   cwd=oracle, env=env, check=True, timeout=150)
    rustc = (ROOT / "artifacts/rust/toolchain/bin" / ("rustc.exe" if os.name == "nt" else "rustc"))
    subprocess.run([sys.executable, HERE.parent / "check-toolchain.py", args.target, "--rustc", rustc], check=True)
    exe = build_dir / ("instance.exe" if os.name == "nt" else "instance")
    subprocess.run([rustc, "--edition=2024", "-Dwarnings", "-O", HERE / "main.rs", "-o", exe],
                   cwd=build_dir, env=env, check=True, timeout=180)
    dll = output / "InstanceOracle.dll"
    tracked = sorted(set(sources) | {HERE / name for name in ("legacy-inputs.json", "main.rs", "unix.rs", "windows.rs", "run.py")})
    receipt = {"native_target": args.target, "dotnet_sdk": sdk, "legacy_reference": pins["reference"],
               "oracle_sha256": sha(dll), "rust_binary_sha256": sha(exe),
               "source_sha256": {path.relative_to(ROOT).as_posix(): sha(path) for path in tracked}
               | {path: sha(oracle / Path(path).name) for path in pins["windows" if os.name == "nt" else "linux"]}}
    return exe, [dotnet, dll], receipt


def observe(root, env, target, exe, oracle, results):
    arch = "arm64" if target.startswith("aarch64-") else "x64"
    identity = subprocess.check_output([*oracle, "identity", root, arch], cwd=root, env=env,
                                       text=True, timeout=25).strip()
    if (os.name == "nt" and not identity.startswith("S-1-")) or (os.name != "nt" and identity != "unix"):
        raise RuntimeError("Invalid oracle owner identity")
    with ExitStack() as children:
        def child(args):
            return children.enter_context(Child(args, root, env))

        def native(role, peer=0):
            return child([exe, role, root, identity, str(peer)])

        def legacy(role):
            return child([*oracle, role, root, arch])

        # The fresh guard stays in the same profile while the unmodified legacy endpoint is active.
        holder = native("writer")
        holder.expect("WRITER_HELD")
        first = legacy("listen")
        first.expect("PRIMARY_READY")
        results.append("legacy_can_still_start_while_only_the_new_file_guard_is_held")
        refused = native("writer")
        refused.expect("WRITER_BUSY")
        refused.success()
        results.append("second_native_writer_refused")

        signal = native("signal", first.proc.pid)
        signal.expect("SECONDARY_SIGNALLED")
        first.expect("SHOW_GUI")
        signal.success()
        first.success()
        results.append("rust_to_shipping_coordinator_show_gui")

        second = legacy("signal")
        server = native("listen", second.proc.pid)
        server.expect("PRIMARY_READY")
        second.send("GO")
        second.expect("SECONDARY_SIGNALLED")
        server.expect("SHOW_GUI")
        second.success()
        server.success()
        results.append("shipping_secondary_to_rust_show_gui")

        holder.send("RELEASE")
        holder.expect("WRITER_RELEASED")
        holder.success()
        next_holder = native("writer")
        next_holder.expect("WRITER_HELD")
        results.append("writer_reacquired_after_orderly_release")
        next_holder.proc.kill()
        next_holder.proc.wait(timeout=10)
        recovered = native("writer")
        recovered.expect("WRITER_HELD")
        recovered.send("RELEASE")
        recovered.expect("WRITER_RELEASED")
        recovered.success()
        results.append("writer_reacquired_after_holder_process_exit")
    if (root / "immich-folder-watch.sock").exists():
        raise RuntimeError("The private activation endpoint survived its listener")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="ifw-ipc-") as temp:
        area = Path(temp).resolve()
        root = area / "profile"
        root.mkdir(mode=0o700)
        (root / ".ifw-instance-fixture").write_bytes(b"synthetic-only\n")
        (root / "writer.lock").touch(mode=0o600, exist_ok=False)
        env = dict(os.environ, HOME=str(area), XDG_CONFIG_HOME=str(area / "config"),
                   XDG_RUNTIME_DIR=str(root), DOTNET_CLI_HOME=str(area), NUGET_PACKAGES=str(area / "packages"),
                   DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_GENERATE_ASPNET_CERTIFICATE="false",
                   DOTNET_ADD_GLOBAL_TOOLS_TO_PATH="0", DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE="1")
        exe, oracle, result = build(args, area / "build", env)
        result["observations"] = []
        try:
            observe(root, env, args.target, exe, oracle, result["observations"])
            result["passed"] = True
        except Exception as err:
            result.update(passed=False, error=str(err))
            raise
        finally:
            (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result["observations"]))


if __name__ == "__main__":
    main()
