"""Assemble a patch and write the JSON the patcher ships.

    python tools/build_patch.py patches/release

reads ``patches/release.hooks.json`` and its source (``patches/release.S``, or the
spec's ``source``) and writes ``src/freakpatch/patches/release.json``. Needs a clang with the Thumb target
(Apple clang and upstream LLVM both have it). The object must have no relocations:
every stock address in the source is a literal constant.
"""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLANG_ARGS = ["--target=thumbv7em-none-eabi", "-mcpu=cortex-m4", "-mthumb", "-c"]


def _sections(elf: bytes) -> dict[str, tuple[int, int, int, int, int]]:
    """``{name: (type, offset, size, link, entsize)}`` for an ELF32 little-endian object."""
    if elf[:4] != b"\x7fELF" or elf[4] != 1 or elf[5] != 1:
        raise ValueError("expected a 32-bit little-endian ELF object")
    (shoff,) = struct.unpack_from("<I", elf, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", elf, 0x2E)
    headers = [struct.unpack_from("<IIIIIIIIII", elf, shoff + i * shentsize) for i in range(shnum)]
    names_off = headers[shstrndx][4]

    def name(off: int) -> str:
        return elf[names_off + off : elf.index(b"\0", names_off + off)].decode()

    return {name(h[0]): (h[1], h[4], h[5], h[6], h[9]) for h in headers}


def assemble(source: Path) -> tuple[bytes, dict[str, int]]:
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / "patch.o"
        subprocess.run(["clang", *CLANG_ARGS, str(source), "-o", str(obj)], check=True)
        elf = obj.read_bytes()
    sections = _sections(elf)
    relocations = [n for n, s in sections.items() if s[0] in (4, 9) and s[2]]  # SHT_RELA, SHT_REL
    if relocations:
        raise ValueError(f"patch object has relocations in {relocations}; use literal addresses")
    _, text_off, text_size, _, _ = sections[".text"]
    code = elf[text_off : text_off + text_size]

    _, sym_off, sym_size, link, entsize = sections[".symtab"]
    str_off = [s for s in sections.values()][link][1]
    text_index = list(sections).index(".text")
    symbols = {}
    for i in range(sym_size // entsize):
        st_name, st_value, _, st_info, _, st_shndx = struct.unpack_from("<IIIBBH", elf, sym_off + i * entsize)
        if st_info >> 4 == 1 and st_shndx == text_index:  # STB_GLOBAL in .text
            sym = elf[str_off + st_name : elf.index(b"\0", str_off + st_name)].decode()
            symbols[sym] = st_value & ~1
    return code, symbols


def main(stem: str) -> None:
    base = ROOT / stem
    spec = json.loads(base.with_suffix(".hooks.json").read_text())
    source = base.parent / spec.get("source", base.name + ".S")
    code, symbols = assemble(source)
    region = int(spec["region"]["end"], 16) - int(spec["region"]["start"], 16)
    if len(code) > region:
        raise ValueError(f"{source.name}: {len(code)} bytes do not fit the {region}-byte region")
    needed = {h["symbol"] for h in spec["hooks"]} | {o["symbol"] for o in spec["options"].values()}
    missing = needed - symbols.keys()
    if missing:
        raise ValueError(f"symbols not exported by {source.name}: {sorted(missing)}")
    patch = {
        **spec,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "symbols": {k: symbols[k] for k in sorted(needed)},
        "code": code.hex(),
    }
    out = ROOT / "src" / "freakpatch" / "patches" / f"{base.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(patch, indent=2) + "\n")
    hooks, edits = len(spec["hooks"]), len(spec["edits"])
    print(f"{out.relative_to(ROOT)}: {len(code)} of {region} bytes, {hooks} hooks, {edits} edits")


if __name__ == "__main__":
    main(sys.argv[1])
