#!/usr/bin/env python3
"""Validate ARM ABI coverage and 16 KB native compatibility of release artifacts."""
from pathlib import Path
import argparse
import re
import subprocess
import tempfile
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument("--aab", required=True)
parser.add_argument("--apk", required=True)
parser.add_argument("--llvm-readelf", required=True)
parser.add_argument("--zipalign", required=True)
args = parser.parse_args()

aab = Path(args.aab)
apk = Path(args.apk)
llvm_readelf = Path(args.llvm_readelf)
zipalign = Path(args.zipalign)
for p in (aab, apk, llvm_readelf, zipalign):
    if not p.exists():
        raise SystemExit(f"ERROR: missing {p}")

abis = ("armeabi-v7a", "arm64-v8a")

with zipfile.ZipFile(aab) as zf:
    names = zf.namelist()
    for abi in abis:
        libs = [n for n in names if n.startswith(f"base/lib/{abi}/") and n.endswith(".so")]
        if not libs:
            raise SystemExit(f"ERROR: AAB contains no {abi} native libraries")
        print(f"AAB {abi}: {len(libs)} native libraries")

    # 16 KB Android devices are 64-bit. Validate every arm64 ELF, including
    # libc++_shared and all SDL satellite libraries, rather than only libmain.so.
    arm64 = sorted(n for n in names if n.startswith("base/lib/arm64-v8a/") and n.endswith(".so"))
    with tempfile.TemporaryDirectory() as td_name:
        td = Path(td_name)
        for index, name in enumerate(arm64):
            out = td / f"{index:03d}-{Path(name).name}"
            out.write_bytes(zf.read(name))
            text = subprocess.check_output([str(llvm_readelf), "-lW", str(out)], text=True)
            load_lines = [line for line in text.splitlines() if re.match(r"\s*LOAD\s", line)]
            if not load_lines:
                raise SystemExit(f"ERROR: no LOAD segments found in {name}")
            for line in load_lines:
                try:
                    align = int(line.split()[-1], 16)
                except (ValueError, IndexError) as exc:
                    raise SystemExit(f"ERROR: could not parse LOAD alignment for {name}: {line}") from exc
                if align < 0x4000:
                    raise SystemExit(f"ERROR: {name} has LOAD alignment {align:#x} < 0x4000")
            print(f"16 KB ELF: OK {name}")

with zipfile.ZipFile(apk) as zf:
    names = zf.namelist()
    for abi in abis:
        libs = [n for n in names if n.startswith(f"lib/{abi}/") and n.endswith(".so")]
        if not libs:
            raise SystemExit(f"ERROR: release APK contains no {abi} native libraries")
        print(f"APK {abi}: {len(libs)} native libraries")

# This is the official package-level check for uncompressed .so alignment.
subprocess.run([str(zipalign), "-c", "-P", "16", "-v", "4", str(apk)], check=True)
print("16 KB APK ZIP alignment: OK")
print("Native release validation: OK")
