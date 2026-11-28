"""Verify the native device replacement, redrawn field and surviving inventory worker."""
import argparse
import json
from pathlib import Path

from device_recovery import verify

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cpu_paint", type=Path)
    print(json.dumps(verify(parser.parse_args().cpu_paint.resolve()), indent=2))
