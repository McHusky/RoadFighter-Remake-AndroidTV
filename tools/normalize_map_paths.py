#!/usr/bin/env python3
"""Normalize original Windows Road Fighter .mg2 asset paths for Android/Linux.

The 2003 map files use backslashes (for example graphics\\road.bmp). On
Android/Linux those are ordinary characters, not directory separators, so
SDL_image cannot find the referenced files. Normalize every map to forward
slashes and verify that each referenced graphics asset exists.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "app" / "src" / "main" / "assets" / "roadfighter"
MAP_DIR = ASSET_ROOT / "maps"
PATH_RE = re.compile(rb"(?<![A-Za-z0-9_.-])(graphics[\\/][A-Za-z0-9_.-]+)")


def main() -> int:
    maps = sorted(MAP_DIR.glob("*.mg2"))
    if not maps:
        print(f"No .mg2 maps found under {MAP_DIR}", file=sys.stderr)
        return 1

    changed = 0
    referenced = set()
    for path in maps:
        data = path.read_bytes()
        normalized = data.replace(b"\\", b"/")
        if normalized != data:
            path.write_bytes(normalized)
            changed += 1
        if b"\\" in normalized:
            print(f"Residual backslash remains in {path}", file=sys.stderr)
            return 1
        for match in PATH_RE.finditer(normalized):
            referenced.add(match.group(1).decode("ascii"))

    missing = [rel for rel in sorted(referenced) if not (ASSET_ROOT / rel).is_file()]
    if missing:
        print("Map references missing packaged assets:", file=sys.stderr)
        for rel in missing:
            print(f"  {rel}", file=sys.stderr)
        return 1

    print(f"Normalized {changed} map file(s); validated {len(referenced)} graphics reference(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
