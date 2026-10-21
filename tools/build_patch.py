"""Assemble a patch and write the JSON the patcher ships.

    python tools/build_patch.py patches/release

reads ``patches/release.hooks.json`` and its source (``patches/release.S``, or the
spec's ``source``) and writes ``src/freakpatch/patches/release.json``. A spec with ``"combine": [names]``
(``patches/release-matrix``) builds each named spec in order and ships them as one patch with
several ``parts``; its own ``drop_hooks`` (sites) put a part's hook back to stock, and its own ``edits``
are added to the parts' edits. A named spec can itself be a combined one (``patches/voice-modes``
starts from ``release-matrix``). Needs a clang with the Thumb target (Apple clang and upstream LLVM
both have it).

Every address is fixed when the patch is built, so the shipped JSON holds finished bytes:

- ``region`` places ``.text``; ``sections`` places each section of a source, and each ships as its own part.
- Relocations are resolved here: absolute words (``.word label``), branches between a source's own sections, and
  ``call F`` / ``jump F`` to a fixed address (``patches/series.inc``).
- A hook with ``next`` chains: the word ``next`` gets the site's current target, which is the stock ``target`` or,
  in a combined build, the earlier part that hooked the site. That part's hook is replaced.
- A ``word`` hook points a word at a symbol: inside a part's code it's filled in there, anywhere else it ships as a
  ``word`` edit.
- ``imports`` lists symbols of earlier parts that a source calls by address, and the address it expects.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from freakpatch import thumb  # noqa: E402

CLANG_ARGS = ["--target=thumbv7em-none-eabi", "-mcpu=cortex-m4", "-mthumb", "-c"]
R_ARM_ABS32, R_ARM_THM_CALL, R_ARM_THM_JUMP24 = 2, 10, 30
SHT_PROGBITS, SHT_SYMTAB, SHT_RELA, SHT_REL, SHF_EXECINSTR, SHN_ABS = 1, 2, 4, 9, 4, 0xFFF1
ABS = "*ABS*"
"""Section name given to absolute symbols, and to the undefined ``F.abs`` that ``call F`` / ``jump F`` relocate
against (its value is the global ``.equ F``'s)."""

Relocation = tuple[str, int, int, str, int]
"""(section, offset, type, symbol's section, symbol's value)"""


def _headers(elf: bytes) -> tuple[list[str], list[tuple[int, ...]]]:
    """Section names and headers ``(name, type, flags, addr, offset, size, link, info, align, entsize)`` of an ELF32
    little-endian object."""
    if elf[:4] != b"\x7fELF" or elf[4] != 1 or elf[5] != 1:
        raise ValueError("expected a 32-bit little-endian ELF object")
    (shoff,) = struct.unpack_from("<I", elf, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", elf, 0x2E)
    headers = [struct.unpack_from("<IIIIIIIIII", elf, shoff + i * shentsize) for i in range(shnum)]
    names_off = headers[shstrndx][4]
    names = [elf[names_off + h[0] : elf.index(b"\0", names_off + h[0])].decode() for h in headers]
    return names, headers


def assemble(source: Path) -> tuple[dict[str, bytes], dict[str, tuple[str, int]], list[Relocation]]:
    """``{section: bytes}`` of the executable sections, ``{symbol: (section, value)}`` (locals too, Thumb bit as
    assembled) and the relocations."""
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / "patch.o"
        subprocess.run(["clang", *CLANG_ARGS, str(source), "-o", str(obj)], check=True)
        elf = obj.read_bytes()
    names, headers = _headers(elf)
    sections = {
        names[i]: elf[h[4] : h[4] + h[5]]
        for i, h in enumerate(headers)
        if h[1] == SHT_PROGBITS and h[2] & SHF_EXECINSTR
    }
    symtab = next(h for h in headers if h[1] == SHT_SYMTAB)
    str_off = headers[symtab[6]][4]

    def name(off: int) -> str:
        return elf[str_off + off : elf.index(b"\0", str_off + off)].decode()

    entries = [struct.unpack_from("<IIIBBH", elf, symtab[4] + 16 * i) for i in range(symtab[5] // 16)]
    absolute = {name(e[0]): e[1] for e in entries if e[0] and e[5] == SHN_ABS}
    symbols: dict[str, tuple[str, int]] = {}
    by_index: list[tuple[str | None, int]] = []
    for st_name, value, _, _, _, shndx in entries:
        sym = name(st_name) if st_name else ""
        section = names[shndx] if 0 < shndx < len(names) else None
        if shndx == SHN_ABS:
            section = ABS
        elif shndx == 0 and sym.endswith(".abs"):  # call F / jump F
            if sym[:-4] not in absolute:
                raise ValueError(f"{source.name}: {sym[:-4]} is not a global .equ")
            section, value = ABS, absolute[sym[:-4]]
        by_index.append((section, value))
        if sym and section in sections and not sym.startswith(("$", ".L")):
            symbols[sym] = (section, value)
    relocations = []
    for h in headers:
        if h[1] == SHT_RELA and h[5]:
            raise ValueError(f"{source.name}: RELA relocations are not supported")
        if h[1] == SHT_REL and names[h[7]] in sections:
            for k in range(h[5] // 8):
                off, info = struct.unpack_from("<II", elf, h[4] + 8 * k)
                section, value = by_index[info >> 8]
                if section is None:
                    raise ValueError(f"{source.name}: {names[h[7]]}+{off:#x} refers to an undefined symbol")
                relocations.append((names[h[7]], off, info & 0xFF, section, value))
    return sections, symbols, relocations


def link(sections: dict[str, bytes], relocations: list[Relocation], place: dict[str, int]) -> dict[str, bytearray]:
    """Each section's bytes with its relocations resolved for the addresses in ``place``."""
    out = {k: bytearray(v) for k, v in sections.items()}
    for section, off, kind, target_section, value in relocations:
        site = place[section] + off
        target = value + (0 if target_section == ABS else place[target_section])
        if kind == R_ARM_ABS32:
            struct.pack_into("<I", out[section], off, target + struct.unpack_from("<I", out[section], off)[0])
        elif kind in (R_ARM_THM_CALL, R_ARM_THM_JUMP24):
            # REL: the addend is the branch as assembled (`bl .` reaches site + 4 - 4).
            addend = thumb.branch_target(site, bytes(out[section][off : off + 4])) - site
            encode = thumb.bl if kind == R_ARM_THM_CALL else thumb.b_w
            out[section][off : off + 4] = encode(site, (target & ~1) + addend)
        else:
            raise ValueError(f"relocation type {kind} at {section}+{off:#x} is not supported")
    return out


def build(base: Path, targets: dict[int, int] | None = None) -> dict:
    """A patch with one source, from ``<base>.hooks.json``, before ``_finish``. ``targets`` holds the current target
    of sites that earlier parts of a combined build hooked; chained hooks there call those instead of stock."""
    spec = json.loads(base.with_suffix(".hooks.json").read_text())
    source = base.parent / spec.get("source", base.name + ".S")
    sections, symbols, relocations = assemble(source)
    regions = spec["sections"] if "sections" in spec else {".text": spec["region"]}
    place = {s: int(r["start"], 16) for s, r in regions.items()}
    missing = set(sections) - set(place)
    if missing:
        raise ValueError(f"{source.name}: no address for {sorted(missing)}")
    for section, region in regions.items():
        room = int(region["end"], 16) - place[section]
        if place[section] % 4 or len(sections.get(section, b"")) > room:
            raise ValueError(f"{source.name}: {section} does not fit its {room}-byte region at {place[section]:#x}")
    code = link(sections, relocations, place)

    def address(sym: str) -> int:
        if sym not in symbols:
            raise ValueError(f"symbols not exported by {source.name}: {sym}")
        section, value = symbols[sym]
        return place[section] + (value & ~1)

    nexts: dict[str, int] = {}
    for hook in (h for h in spec["hooks"] if "next" in h):
        site = int(hook["site"], 16)
        target = (targets or {}).get(site, int(hook["target"], 16))
        if nexts.setdefault(hook["next"], target) != target:
            raise ValueError(f"{source.name}: sites sharing {hook['next']} have different targets")
        section, value = symbols[hook["next"]]
        struct.pack_into("<I", code[section], value, target | 1)

    words = [h for h in spec["hooks"] if h["kind"] == "word"]
    hooks = [h for h in spec["hooks"] if h["kind"] != "word"]
    needed = {h["symbol"] for h in spec["hooks"]} | {o["symbol"] for o in spec["options"].values()}
    if "cc_table" in spec:
        needed.add(spec["cc_table"]["symbol"])
    absent = needed - symbols.keys()
    if absent:
        raise ValueError(f"symbols not exported by {source.name}: {sorted(absent)}")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    parts = [
        {
            "name": spec["name"] if section == ".text" else f"{spec['name']}{section}",
            "region": region,
            "source_sha256": source_hash,
            "symbols": {k: symbols[k][1] & ~1 for k in sorted(needed) if symbols[k][0] == section},
            "code": bytes(code.get(section, b"")).hex(),
        }
        for section, region in regions.items()
    ]
    built = {k: v for k, v in spec.items() if k not in ("sections", "imports")}
    if "sections" in spec:
        built["parts"] = parts
    else:
        built.update({k: parts[0][k] for k in ("source_sha256", "symbols", "code")})
    built["hooks"] = hooks
    built["_words"] = [{**h, "value": f"{address(h['symbol']) | 1:#010x}"} for h in words]
    built["_addresses"] = {k: address(k) for k in symbols}
    built["_imports"] = spec.get("imports", {})
    return built


def _parts(unit: dict) -> list[dict]:
    """A built unit's parts: a combined build's own list, or the unit itself."""
    return unit.get("parts", [unit])


def _address(unit: dict, symbol: str) -> int:
    for p in _parts(unit):
        if symbol in p["symbols"]:
            return int(p["region"]["start"], 16) + p["symbols"][symbol]
    raise ValueError(f"{unit['name']} has no symbol {symbol!r}")


def _finish(patch: dict) -> dict:
    """``patch`` as shipped: each ``word`` hook filled into the part whose code holds its site, or added to the
    edits, and the build's own bookkeeping (keys starting with ``_``) dropped."""
    patch = {**patch, "edits": list(patch["edits"])}
    if "parts" in patch:
        patch["parts"] = [dict(p) for p in patch["parts"]]
    for word in patch.get("_words", []):
        site = int(word["site"], 16)
        for part in _parts(patch):
            start = int(part["region"]["start"], 16)
            code = bytearray.fromhex(part["code"])
            if start <= site < start + len(code):
                struct.pack_into("<I", code, site - start, int(word["value"], 16))
                part["code"] = code.hex()
                break
        else:
            patch["edits"].append({"site": word["site"], "kind": "word", "value": word["value"], "was": word["was"]})
    return {k: v for k, v in patch.items() if not k.startswith("_")}


def combine(spec: dict, units: list[dict]) -> dict:
    """One patch from several built units, each a one-source patch or a combined build, in order. A chained hook
    replaces an earlier unit's hook at its site."""
    dropped = {int(d["site"], 16) for d in spec.get("drop_hooks", [])}
    hooks: list[dict] = []
    for unit in units:
        for h in unit["hooks"]:
            if "next" in h:
                hooks = [k for k in hooks if k["site"] != h["site"]]
            hooks.append(h)
    kept = [h for h in hooks if int(h["site"], 16) not in dropped]
    if len(kept) != len(hooks) - len(dropped):
        raise ValueError("a dropped hook is not a hook of any part")
    hooks = kept
    addresses = {k: v for u in units for k, v in u.get("_addresses", {}).items()}
    for unit in units:
        for symbol, at in unit.get("_imports", {}).items():
            if addresses.get(symbol) != int(at, 16):
                raise ValueError(f"{unit['name']} expects {symbol} at {at}, it is at {addresses.get(symbol, 0):#x}")
    parts = [p for u in units for p in _parts(u)]
    owner = {p["name"]: u["name"] for u in units for p in _parts(u)}
    own = {"name": spec["name"], "hooks": [], "edits": spec.get("edits", [])}
    regions = sorted((int(p["region"]["start"], 16), int(p["region"]["end"], 16), p["name"]) for p in parts)
    for (_, end, a), (start, _, b) in itertools.pairwise(regions):
        if start < end:
            raise ValueError(f"regions of {a} and {b} overlap")
    spans = sorted(
        (image, start, start + n, u["name"])
        for u in [*units, own]
        for image, start, n in _site_spans({**u, "hooks": [h for h in u["hooks"] if h in hooks]})
    )
    for (ia, _, end, a), (ib, start, _, b) in itertools.pairwise(spans):
        if ia == ib and start < end:
            raise ValueError(f"{a} and {b} patch overlapping bytes at {start:#x}")
    for image, start, end, name in spans:
        for r_start, r_end, part in regions:
            if image == "main" and owner[part] != name and start < r_end and r_start < end:
                raise ValueError(f"{name} patches {start:#x}, inside the code region of {part}")
    symbols = [s for p in parts for s in p["symbols"]]
    if len(symbols) != len(set(symbols)):
        raise ValueError("two parts export the same symbol")
    options = [k for u in units for k in u["options"]]
    if len(options) != len(set(options)):
        raise ValueError("two parts declare the same option")
    tables = [u["cc_table"] for u in units if "cc_table" in u]
    if len(tables) > 1:
        raise ValueError("more than one part has a CC table")
    keys = ("name", "region", "source", "source_sha256", "symbols", "code")
    return {
        "name": spec["name"],
        "description": spec["description"],
        "parts": [{k: p[k] for k in keys if k in p} for p in parts],
        "hooks": hooks,
        "edits": [e for u in [*units, own] for e in u["edits"]],
        "options": {k: v for u in units for k, v in u["options"].items()},
        **({"cc_table": tables[0]} if tables else {}),
        "_words": [w for u in units for w in u.get("_words", [])],
        "_addresses": addresses,
    }


def _site_spans(part: dict) -> list[tuple[str, int, int]]:
    """(image, site, length) of every hook and edit: 4 bytes, a word, a movw, a halfword, or a string's length."""
    return [("main", int(h["site"], 16), 4) for h in part["hooks"]] + [
        (
            e.get("image", "main"),
            int(e["site"], 16),
            int(e["length"]) if e["kind"] == "string" else 2 if e["kind"] == "half" else 4,
        )
        for e in part["edits"]
    ]


def _build_spec(base: Path, targets: dict[int, int]) -> dict:
    spec = json.loads(base.with_suffix(".hooks.json").read_text())
    if "combine" not in spec:
        return build(base, targets)
    units = []
    for name in spec["combine"]:
        unit = _build_spec(base.parent / name, targets)
        targets.update({int(h["site"], 16): _address(unit, h["symbol"]) for h in unit["hooks"]})
        units.append(unit)
    for d in spec.get("drop_hooks", []):
        targets.pop(int(d["site"], 16), None)
    return combine(spec, units)


def shipped(base: Path) -> dict:
    """The JSON shipped for ``patches/<name>``: built, combined or not."""
    return _finish(_build_spec(base, {}))


def main(stem: str) -> None:
    base = ROOT / stem
    patch = shipped(base)
    out = ROOT / "src" / "freakpatch" / "patches" / f"{base.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(patch, indent=2) + "\n")
    for p in _parts(patch):
        size = int(p["region"]["end"], 16) - int(p["region"]["start"], 16)
        print(f"{out.relative_to(ROOT)}: {p['name']}: {len(p['code']) // 2} of {size} bytes")
    print(f"{len(patch['hooks'])} hooks, {len(patch['edits'])} edits")


if __name__ == "__main__":
    main(sys.argv[1])
