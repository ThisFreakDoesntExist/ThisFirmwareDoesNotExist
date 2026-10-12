"""Apply a patch to the user's own official MicroFreak update file.

Only the latest official firmware is accepted, identified by the SHA-256 of the whole
``.mff``. The main image keeps its exact stock length: MicroFreak hardware hangs at the
boot logo with any longer image. A patch's code goes into a code region inside the
image that the patch itself makes unreachable (see ``docs/release-patch.md``; a combined
build has one such region per part), stock
instructions at the hook sites become branches into it, and a few single instructions
or words are rewritten in place. No firmware bytes are shipped with the patcher:
everything else comes from the user's file.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from importlib import resources

from freakpatch import mff, thumb

LATEST_VERSION = "5.0.0.2084"
LATEST_SHA256 = "c2b405e3c8565b7b73b4dd06522559458190082a8ba633cc5f1bcc43dc64332c"
MAIN_BASE = 0x0800C000
"""Flash address of the first payload byte of the main image."""
STOCK_CCS = frozenset({2, 5, 9, 10, 12, 13, 23, 24, 26, 28, 29, 83, 91, 92, 93, 94, 102, 103, 105, 106})
"""MIDI CCs the stock firmware maps to parameters (read from the constructed parameter object)."""
RESERVED_CCS = frozenset(
    {0, 1, 4, 6, 7, 8, 10, 11, *range(32, 64), *range(64, 70), 84, 88, *range(91, 102), *range(120, 128)}
)
"""CCs MIDI gives a fixed meaning: bank select, mod wheel, foot, data entry, volume, balance, pan, expression, the
14-bit LSBs, pedals, portamento control, high-resolution velocity, effect depths, data increment and RPN/NRPN, and
channel mode. A patch's CC table must not use them."""


class PatchError(ValueError):
    pass


@dataclass(frozen=True)
class Hook:
    site: int
    kind: str  # "bl" or "b.w"
    symbol: str


@dataclass(frozen=True)
class Edit:
    site: int
    kind: str  # "movw", "word" or "string"
    value: int = 0
    reg: int = 0
    text: str = ""
    length: int = 0
    """For "string": the NUL-terminated text replaces ``length`` bytes, padded with NULs."""

    @classmethod
    def from_spec(cls, e: dict[str, object]) -> Edit:
        if e["kind"] == "string":
            return cls(int(str(e["site"]), 16), "string", text=str(e["text"]), length=int(str(e["length"])))
        return cls(int(str(e["site"]), 16), str(e["kind"]), int(str(e["value"]), 16), int(str(e.get("reg", 0))))

    def encode(self) -> bytes:
        if self.kind == "movw":
            return thumb.movw(self.reg, self.value)
        if self.kind == "string":
            data = self.text.encode("ascii") + b"\0"
            if len(data) > self.length:
                raise PatchError(f"{self.text!r} does not fit {self.length} bytes")
            return data.ljust(self.length, b"\0")
        return struct.pack("<I", self.value)


@dataclass(frozen=True)
class Part:
    """Code placed in one region; ``symbols`` are offsets into ``code``."""

    region: tuple[int, int]
    code: bytes
    symbols: dict[str, int]

    @classmethod
    def from_spec(cls, raw: dict) -> Part:  # type: ignore[type-arg]
        region = (int(raw["region"]["start"], 16), int(raw["region"]["end"], 16))
        return cls(region, bytes.fromhex(raw["code"]), raw["symbols"])


@dataclass(frozen=True)
class Patch:
    name: str
    description: str
    parts: tuple[Part, ...]
    """One per code region: a single patch has one, a combined build (``parts`` in its JSON) several."""
    hooks: tuple[Hook, ...]
    edits: tuple[Edit, ...]
    options: dict[str, dict[str, object]]
    cc_table: tuple[str, int] | None = None
    """(symbol, length) of a table of MIDI CCs the patch maps, 0 = none."""

    @classmethod
    def load(cls, name: str) -> Patch:
        raw = json.loads(resources.files("freakpatch.patches").joinpath(f"{name}.json").read_text())
        table = raw.get("cc_table")
        parts = tuple(Part.from_spec(p) for p in raw.get("parts", [raw]))
        symbols = [s for part in parts for s in part.symbols]
        if len(symbols) != len(set(symbols)):
            raise PatchError(f"{name}: two parts export the same symbol")
        return cls(
            name=raw["name"],
            description=raw.get("description", ""),
            parts=parts,
            hooks=tuple(Hook(int(h["site"], 16), h["kind"], h["symbol"]) for h in raw["hooks"]),
            edits=tuple(Edit.from_spec(e) for e in raw["edits"]),
            options=raw["options"],
            cc_table=(table["symbol"], table["length"]) if table else None,
        )

    @property
    def region(self) -> tuple[int, int]:
        """The code region of a single-region patch."""
        return self._single().region

    @property
    def code(self) -> bytes:
        """The code of a single-region patch."""
        return self._single().code

    @property
    def symbols(self) -> dict[str, int]:
        """Every part's symbols, as offsets into that part's code."""
        return {k: v for part in self.parts for k, v in part.symbols.items()}

    def _single(self) -> Part:
        if len(self.parts) != 1:
            raise PatchError(f"{self.name} has {len(self.parts)} code regions")
        return self.parts[0]

    def part_of(self, symbol: str) -> Part:
        for part in self.parts:
            if symbol in part.symbols:
                return part
        raise PatchError(f"{self.name} has no symbol {symbol!r}")

    def address(self, symbol: str) -> int:
        part = self.part_of(symbol)
        return part.region[0] + part.symbols[symbol]

    def mapped_ccs(self) -> list[int]:
        """The CCs in the patch's CC table, in table order, without its 0 (no CC) entries."""
        if self.cc_table is None:
            return []
        symbol, length = self.cc_table
        part = self.part_of(symbol)
        offset = part.symbols[symbol]
        return [cc for cc in part.code[offset : offset + length] if cc]

    def touched(self) -> set[int]:
        """Payload offsets this patch may change."""
        spans = [(h.site, 4) for h in self.hooks] + [(e.site, len(e.encode())) for e in self.edits]
        regions = {
            i for start, end in (p.region for p in self.parts) for i in range(start - MAIN_BASE, end - MAIN_BASE)
        }
        return regions | {s - MAIN_BASE + i for s, n in spans for i in range(n)}


def check_latest(raw: bytes) -> None:
    digest = hashlib.sha256(raw).hexdigest()
    if digest != LATEST_SHA256:
        raise PatchError(
            f"this is not the official MicroFreak firmware {LATEST_VERSION} update file "
            f"(SHA-256 {digest}). Only that file is supported: download it from Arturia "
            "or use the copy MIDI Control Center keeps, and don't patch an already patched file."
        )


def _release_cc(value: int, taken: list[int]) -> int:
    if not 1 <= value <= 119 or value in STOCK_CCS:
        raise PatchError(f"CC {value} is not available: use 1-119, not one of the stock CCs {sorted(STOCK_CCS)}")
    if value in taken:
        raise PatchError(f"CC {value} is not available: the patch maps it to the mod matrix")
    return value


def _check_cc_table(patch: Patch, release_cc: int | None) -> None:
    """The patch's CC table: unique CCs that collide with nothing stock, MIDI or the Release CC uses."""
    ccs = patch.mapped_ccs()
    if len(ccs) != len(set(ccs)):
        raise PatchError(f"{patch.name}: its CC table maps a CC twice")
    clash = set(ccs) & (STOCK_CCS | RESERVED_CCS | ({release_cc} if release_cc is not None else set()))
    if clash or any(cc > 119 for cc in ccs):
        raise PatchError(f"{patch.name}: its CC table uses CCs it must not: {sorted(clash) or ccs}")


def apply(raw: bytes, patch: Patch, release_cc: int | None = None) -> bytes:
    """The patched ``.mff`` for the official update file ``raw``."""
    check_latest(raw)
    update = mff.Update.from_bytes(raw)
    name = update.main_name
    image = update.read(name)
    payload = bytearray(mff.main_payload(image))

    codes = {}
    for part in patch.parts:
        start, end = part.region
        if start % 4 or len(part.code) > end - start or end > MAIN_BASE + len(payload):
            raise PatchError(f"{patch.name}: code does not fit its region {start:#x}-{end:#x}")
        codes[start] = bytearray(part.code)
    if release_cc is not None:
        if "release_cc" not in patch.options:
            raise PatchError(f"{patch.name} has no Release CC")
        symbol = str(patch.options["release_cc"]["symbol"])
        part = patch.part_of(symbol)
        codes[part.region[0]][part.symbols[symbol]] = _release_cc(release_cc, patch.mapped_ccs())
    elif "release_cc" in patch.options:
        release_cc = int(str(patch.options["release_cc"]["default"]))
    _check_cc_table(patch, release_cc)
    for start, code in codes.items():
        payload[start - MAIN_BASE : start - MAIN_BASE + len(code)] = code

    for hook in patch.hooks:
        encode = thumb.bl if hook.kind == "bl" else thumb.b_w
        offset = hook.site - MAIN_BASE
        payload[offset : offset + 4] = encode(hook.site, patch.address(hook.symbol))
    for edit in patch.edits:
        offset = edit.site - MAIN_BASE
        data = edit.encode()
        payload[offset : offset + len(data)] = data

    out = update.with_member(name, mff.build_image(image[: mff.HEADER_LEN], bytes(payload))).to_bytes()
    verify(raw, out, patch)
    return out


def verify(raw: bytes, out: bytes, patch: Patch) -> None:
    """Self-check a patched file: same length, and only the patch's own bytes changed."""
    before, after = mff.Update.from_bytes(raw), mff.Update.from_bytes(out)
    if [m.info.filename for m in before.members] != [m.info.filename for m in after.members]:
        raise PatchError("member list changed")
    name = before.main_name
    for m in before.members:
        if m.info.filename != name and after.read(m.info.filename) != m.data:
            raise PatchError(f"{m.info.filename} changed")
    old_image, new_image = before.read(name), after.read(name)
    if len(new_image) != len(old_image):
        raise PatchError(f"main image is {len(new_image)} bytes, stock is {len(old_image)}: it must keep its length")
    old, new = mff.main_payload(old_image), mff.main_payload(new_image)
    changed = {i for i in range(len(old)) if old[i] != new[i]}
    stray = changed - patch.touched()
    if stray:
        raise PatchError(f"unexpected change at {MAIN_BASE + min(stray):#010x}")
    for hook in patch.hooks:
        if thumb.branch_target(hook.site, new[hook.site - MAIN_BASE :]) != patch.address(hook.symbol):
            raise PatchError(f"hook at {hook.site:#010x} does not reach {hook.symbol}")
    for edit in patch.edits:
        if (data := edit.encode()) != new[edit.site - MAIN_BASE : edit.site - MAIN_BASE + len(data)]:
            raise PatchError(f"edit at {edit.site:#010x} missing")
