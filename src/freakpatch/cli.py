"""``freakpatch IN.mff [-o OUT.mff]``: patch your own official MicroFreak update file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from freakpatch.patcher import LATEST_VERSION, Patch, PatchError, apply

PATCHES = ("release", "release-matrix", "matrix-cc", "diag-region", "diag-hook")
"""``release`` is the hardware-tested feature, ``release-matrix`` adds the mod matrix over MIDI CC to it, and
``matrix-cc`` is that on its own; ``release-matrix`` also patches the OLED chip's image, so the envelope curve
draws Decay and Release separately. The ``diag-*`` builds check placement on hardware first."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="freakpatch", description=__doc__)
    parser.add_argument("firmware", type=Path, nargs="?", help=f"official MicroFreak {LATEST_VERSION} .mff")
    parser.add_argument("-o", "--output", type=Path, help="patched .mff to write (default: <firmware>_<patch>.mff)")
    parser.add_argument("--patch", choices=PATCHES, default="release", help="which build (default: release)")
    parser.add_argument("--release-cc", type=int, default=None, help="MIDI CC for Release (default 72)")
    parser.add_argument("--list", action="store_true", help="describe the available patches and exit")
    args = parser.parse_args(argv)
    if args.list:
        for name in PATCHES:
            print(f"{name:15s} {Patch.load(name).description}")
        return 0
    if args.firmware is None:
        parser.error("the official firmware file is required")
    if not args.firmware.is_file():
        parser.error(f"{args.firmware} not found")
    output = args.output or args.firmware.with_name(f"{args.firmware.stem}_{args.patch}.mff")
    if output.resolve() == args.firmware.resolve():
        parser.error("refusing to overwrite the official file; choose another output path")
    try:
        out = apply(args.firmware.read_bytes(), Patch.load(args.patch), release_cc=args.release_cc)
    except PatchError as e:
        print(f"freakpatch: {e}", file=sys.stderr)
        return 1
    output.write_bytes(out)
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
