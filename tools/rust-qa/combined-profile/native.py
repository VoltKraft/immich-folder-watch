"""Link and exercise one profile on the actual compiler host in a synthetic directory."""
import os
import shutil
from pathlib import Path
import subprocess
import sys

from sources import HERE, QA, ROOT, read, sha256, source_config, source_profile


def linux_namespace(toolchain, vendor, build, fixture, flags, alternate_profile=None, replacement=None):
    command = ["bwrap", "--die-with-parent", "--unshare-all", "--new-session", "--clearenv",
               "--ro-bind", "/usr", "/usr", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
               "--dir", "/home/probe", "--dir", "/cargo"]
    for name in ("bin", "lib", "lib64"):
        path = Path("/") / name
        if path.is_symlink():
            command += ["--symlink", str(path.readlink()), str(path)]
        elif path.is_dir():
            command += ["--ro-bind", str(path), str(path)]
    for original in ("/etc/alternatives", "/etc/ld.so.cache"):
        if Path(original).exists():
            command += ["--ro-bind", original, original]
    for path, destination in (
        (toolchain, "/toolchain"), (vendor, "/vendor"), (ROOT / "rust/Cargo.toml", "/project/rust/Cargo.toml"),
        (ROOT / "rust/crates", "/project/rust/crates"), (ROOT / "rust/assets/fonts", "/project/rust/assets/fonts"),
        (source_profile.SOURCES, "/project/tools/rust-qa/gui/artifacts/text"),
        (source_profile.FONTS, "/fonts"), (QA / "gui/src/fonts.rs", "/project/tools/rust-qa/gui/src/fonts.rs"),
        (fixture, "/fixture"),
    ):
        command += ["--ro-bind", str(path), destination]
    command += ["--bind" if alternate_profile else "--ro-bind", str(alternate_profile or HERE),
                "/project/tools/rust-qa/combined-profile"]
    if replacement:
        command += ["--ro-bind", str(replacement), "/changed-plasma"]
    command += ["--bind", str(build), "/build", "--chdir", "/project/tools/rust-qa/combined-profile"]
    for name, value in {"HOME": "/home/probe", "PATH": "/toolchain/bin:/usr/bin", "CARGO_HOME": "/cargo",
                        "CARGO_NET_OFFLINE": "true", "CARGO_TARGET_DIR": "/build",
                        "IFW_QA_FALLBACK_DIR": "/fonts", "LIBSQLITE3_FLAGS": flags,
                        "LIBSQLITE3_SYS_USE_PKG_CONFIG": "0", "LC_ALL": "C"}.items():
        command += ["--setenv", name, value]
    command += ["--setenv", "IFW_QA_COMBINED_HEADLESS", "private-namespace"]
    return command + ["--"]


def linux_renderer_symbols(binary, output, env):
    symbols = subprocess.check_output(["nm", "--defined-only", "--demangle", str(binary)], env=env, encoding="utf-8")
    entry = [row for row in symbols.splitlines() if row.endswith(" eframe::run_native")]
    vulkan = [row for row in symbols.splitlines() if "wgpu_hal::vulkan" in row]
    if not entry or not vulkan:
        raise ValueError("ELF lacks the native eframe entry or Vulkan backend")
    output.write_text("\n".join([*entry, vulkan[0]]) + "\n", encoding="utf-8", newline="\n")
    return {"eframeEntrySymbols": len(entry), "vulkanSymbols": len(vulkan), "sampleSha256": sha256(output)}


def run_native(target, toolchain, vendor, build, output, env, jobs):
    sqlite = read(QA / "storage/inputs.json")["sqlite"]
    subprocess.run([sys.executable, str(QA / "check-toolchain.py"), target, "--rustc",
                    str(toolchain / "bin" / ("rustc.exe" if os.name == "nt" else "rustc"))],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    build.mkdir(exist_ok=True)
    fixture = output / "synthetic-root"
    fixture.mkdir()
    sample = fixture / "sample.txt"
    sample.write_bytes(b"combined fixture\n")
    binary_name = "ifw-combined-assessment" + (".exe" if os.name == "nt" else "")
    binary = build / target / "release" / binary_name
    if sys.platform == "linux":
        # The legacy Linux worker persists the complete 100 ns ticks of this file.
        mtime_ns = 1_795_219_200_000_000_199
        os.utime(sample, ns=(mtime_ns, mtime_ns))
        if sample.stat().st_mtime_ns != mtime_ns:
            raise ValueError("The synthetic filesystem did not preserve the requested nanoseconds")
        prefix = linux_namespace(toolchain, vendor, build, fixture, sqlite["flags"])
        config = source_config(Path("/vendor"))
        cargo = "/toolchain/bin/cargo"
        subject = [f"/build/{target}/release/{binary_name}", "/fixture"]
        isolation = "private Linux mount, network, process, IPC and user namespaces"
    else:
        if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
            raise ValueError("Windows native execution requires the disposable GitHub-hosted runner")
        prefix = []
        config = source_config(vendor)
        cargo = str(toolchain / "bin/cargo.exe")
        subject = [str(binary), str(fixture)]
        isolation = "disposable GitHub-hosted Windows runner"
    env = dict(env, IFW_QA_FALLBACK_DIR=str(source_profile.FONTS), CARGO_TARGET_DIR=str(build),
               LIBSQLITE3_FLAGS=sqlite["flags"], LIBSQLITE3_SYS_USE_PKG_CONFIG="0")

    def step(name, args):
        with (output / name).open("wb") as log:
            subprocess.run([*prefix, *args], env=env, cwd=HERE, check=True,
                           stdout=log, stderr=subprocess.STDOUT, timeout=2400)

    common = ["--release", "--frozen", "--target", target, "--jobs", str(jobs), *config]
    step("build.log", [cargo, "build", *common, "--message-format=json-render-diagnostics"])
    step("clippy.log", [cargo, "clippy", *common, "--all-targets", "--", "-D", "warnings"])
    step("smoke.json", subject)
    observed = read(output / "smoke.json")
    if (observed["marker"] != "combined-profile-v1" or observed["sqliteSourceId"] != sqlite["source_id"]
            or not observed["sqliteExtensionLoadingOmitted"] or observed["tessellatedPrimitives"] <= 0
            or observed["roundTrip"] != {"file": "sample.txt", "utc": "2026-11-21T00:00:00.0000001+00:00"}
            or observed["websocketPing"] != "abc"):
        raise ValueError("Unexpected combined native smoke evidence")
    renderer = "winit-refused-missing-display" if "linux" in target else "native-eframe-function-pointer"
    if observed["nativeRenderer"] != renderer:
        raise ValueError("Missing native eframe entry witness")
    platform = observed["platform"]
    if ("linux" in target and platform != {"binding": "wayland-interface-and-portal-name", "kdeBlurManagerVersion": 1}
            or "windows" in target and platform != {"binding": "windows-shell-notifyicon-layout"}):
        raise ValueError("Combined platform binding witness differs")
    answer = {"target": target, "isolation": isolation, "binarySha256": sha256(binary),
              "buildLogSha256": sha256(output / "build.log"), "clippyLogSha256": sha256(output / "clippy.log"),
              "smokeSha256": sha256(output / "smoke.json"), "sqliteFlags": sqlite["flags"]}
    if sys.platform == "linux":
        answer["sampleMtimeNs"] = mtime_ns
        answer["nativeRendererSymbols"] = linux_renderer_symbols(binary, output / "renderer-symbols.txt", env)
        imports = ["readelf", "--wide", "--dynamic", str(binary)]
    else:
        observer = shutil.which("dumpbin.exe", path=env["PATH"])
        if not observer:
            raise ValueError("The native Visual Studio dumpbin observer is required")
        imports = [observer, "/nologo", "/dependents", str(binary)]
    with (output / "linked-libraries.txt").open("wb") as log:
        subprocess.run(imports, check=True, stdout=log, env=env)
    answer["linkedLibrariesSha256"] = sha256(output / "linked-libraries.txt")
    return answer
