#!/usr/bin/env python3
"""Create a tiny synthetic video for ingest tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/sample.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=320x240:d=0.5",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        return result.returncode
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
