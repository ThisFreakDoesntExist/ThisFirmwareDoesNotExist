"""Print an .mff's info.json and per-image checksums, and write the main image's payload.

    python3 -I tools/ghidra/extract_main.py microfreak_Firmware_Update_5.0.0.2084.mff main500.bin

The payload is the main image with its 64-byte header and trailing checksum byte
removed: load it at 0x0800C000. Standard library only, so it runs without the package.
"""

import functools
import json
import sys
import zipfile
from pathlib import Path

src, out = sys.argv[1], Path(sys.argv[2])
with zipfile.ZipFile(src) as z:
    print(json.dumps(json.loads(z.read("info.json")), indent=1))
    for name in z.namelist():
        data = z.read(name)
        if name.endswith(".bin"):
            x = functools.reduce(lambda a, b: a ^ b, data[0x40:], 0)
            print(f"{name}: size={len(data)} b0={data[0]:#x} b1={data[1]:#x} last={data[-1]:#x} xor(0x40..)={x:#x}")
        if name.startswith("nanowave_main"):
            out.write_bytes(data[0x40:-1])
