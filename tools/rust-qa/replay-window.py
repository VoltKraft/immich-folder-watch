"""Compare Rust window policy with the observed C# lifecycle corpus."""

import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, help="compiled window_trace example")
    args = parser.parse_args()
    data = Path(__file__).resolve().parents[2] / "rust/tests/fixtures/lifecycle/window.json"
    corpus = json.loads(data.read_text(encoding="utf-8"))
    for case in corpus["cases"]:
        commands = "".join(step["command"] + "\n" for step in case["steps"])
        expected = [" ".join(str(step[key]).lower() for key in ("visible", "closed", "trayUnavailable"))
                    for step in case["steps"]]
        actual = subprocess.run([args.executable.resolve()], input=commands, encoding="utf-8",
                                check=True, capture_output=True, timeout=10).stdout.splitlines()
        if actual != expected:
            raise SystemExit(f"{case['id']} mismatch\nexpected {expected}\nactual   {actual}")
    print(f"Matched {len(corpus['cases'])} legacy lifecycle traces.")


if __name__ == "__main__":
    main()
