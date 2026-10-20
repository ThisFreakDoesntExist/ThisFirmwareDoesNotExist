"""Apply a patch to the user's own official MicroFreak update file.

Only the latest official firmware is accepted, identified by the SHA-256 of the whole
``.mff``. A patch's code goes into code regions inside the image that the patch itself
makes unreachable (see ``docs/release-patch.md``; a combined build has one such region
per part), or after the stock image (``docs/free-space-and-dead-code.md``). Stock
instructions at the hook sites become branches into it, and a few single instructions
or words are rewritten in place. An edit can also target the OLED chip's image, which
keeps its length and gets a fresh checksum. No firmware bytes are shipped with the patcher:
everything else comes from the user's file.

The main image keeps its stock length unless a part is appended. Then it grows to cover
the appended code: zeros up to ``APPEND_BASE``, ``0xFF`` (erased flash) after it, and
``0xFF`` padding so the image (header, payload and checksum byte) is a multiple of 16
bytes. The bootloader hangs on a last block that isn't a whole number of words.
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
MAIN_END = 0x08080000
"""End of the flash the bootloader erases for the main image (sectors 3-7): payload and checksum byte must end by
here."""
APPEND_BASE = 0x0807FA60
"""First 16-byte boundary after the stock main payload (which ends at ``0x0807FA5F``, where its checksum byte is
flashed): appended code starts here or later."""
APPEND_ALIGN = 16
"""An image with appended code is padded to a multiple of this, header and checksum byte included."""
OLED_BASE = 0x08000000
"""Flash address of the first payload byte of the OLED I/O chip image."""
IMAGES = {"main": (mff.MAIN_IMAGE_PREFIX, MAIN_BASE), "oled": (mff.OLED_IMAGE_PREFIX, OLED_BASE)}
"""Images an edit can target: file name prefix in the ``.mff`` and payload base address. Hooks and code regions are
always in the main image."""
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
    kind: str  # "movw", "word", "half" (one 16-bit Thumb instruction) or "string"
    value: int = 0
    reg: int = 0
    text: str = ""
    length: int = 0
    """For "string": the NUL-terminated text replaces ``length`` bytes, padded with NULs."""
    image: str = "main"
    """Key of ``IMAGES``: which image ``site`` is in."""

    @classmethod
    def from_spec(cls, e: dict[str, object]) -> Edit:
        site, image = int(str(e["site"]), 16), str(e.get("image", "main"))
        if image not in IMAGES:
            raise PatchError(f"edit at {site:#010x}: unknown image {image!r}")
        if e["kind"] == "string":
            return cls(site, "string", text=str(e["text"]), length=int(str(e["length"])), image=image)
        return cls(site, str(e["kind"]), int(str(e["value"]), 16), int(str(e.get("reg", 0))), image=image)

    def encode(self) -> bytes:
        if self.kind == "movw":
            return thumb.movw(self.reg, self.value)
        if self.kind == "string":
            data = self.text.encode("ascii") + b"\0"
            if len(data) > self.length:
                raise PatchError(f"{self.text!r} does not fit {self.length} bytes")
            return data.ljust(self.length, b"\0")
        if self.kind == "half":
            return struct.pack("<H", self.value)
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

    def images(self) -> list[str]:
        """Keys of ``IMAGES`` this patch changes, main first."""
        return ["main", *sorted({e.image for e in self.edits} - {"main"})]

    def touched(self, image: str = "main") -> set[int]:
        """Payload offsets of ``image`` this patch may change."""
        base = IMAGES[image][1]
        spans = [(e.site, len(e.encode())) for e in self.edits if e.image == image]
        if image != "main":
            return {s - base + i for s, n in spans for i in range(n)}
        spans += [(h.site, 4) for h in self.hooks]
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


def grown(payload: bytes, patch: Patch) -> bytearray:
    """The stock main ``payload`` extended to hold ``patch``'s appended code, with its fill and padding but not the
    code; unchanged if nothing is appended."""
    out = bytearray(payload)
    ends = [p.region[0] + len(p.code) for p in patch.parts if p.region[0] >= APPEND_BASE]
    if not ends:
        return out
    out += bytes(APPEND_BASE - MAIN_BASE - len(out))
    out += b"\xff" * (max(ends) - MAIN_BASE - len(out))
    out += b"\xff" * (-(mff.HEADER_LEN + len(out) + 1) % APPEND_ALIGN)
    if MAIN_BASE + len(out) + 1 > MAIN_END:
        raise PatchError(f"{patch.name}: the padded main image passes {MAIN_END:#x}")
    return out


def apply(raw: bytes, patch: Patch, release_cc: int | None = None) -> bytes:
    """The patched ``.mff`` for the official update file ``raw``."""
    check_latest(raw)
    update = mff.Update.from_bytes(raw)
    name = update.main_name
    image = update.read(name)
    stock_end = MAIN_BASE + len(mff.main_payload(image))
    payload = grown(mff.main_payload(image), patch)

    codes = {}
    for part in patch.parts:
        start, end = part.region
        limit = MAIN_END - 1 if start >= APPEND_BASE else stock_end
        if start % 4 or len(part.code) > end - start or end > limit:
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
    payloads = {"main": payload}
    for edit in patch.edits:
        if edit.image not in payloads:
            payloads[edit.image] = bytearray(mff.main_payload(update.read(update.image_name(IMAGES[edit.image][0]))))
        offset = edit.site - IMAGES[edit.image][1]
        data = edit.encode()
        if not 0 <= offset <= len(payloads[edit.image]) - len(data):
            raise PatchError(f"edit at {edit.site:#010x} is outside the {edit.image} image")
        payloads[edit.image][offset : offset + len(data)] = data

    for key, data in payloads.items():
        member = update.image_name(IMAGES[key][0])
        update = update.with_member(member, mff.build_image(update.read(member)[: mff.HEADER_LEN], bytes(data)))
    out = update.to_bytes()
    verify(raw, out, patch)
    return out


def verify(raw: bytes, out: bytes, patch: Patch) -> None:
    """Self-check a patched file: every image keeps its length (the main image grows only by the patch's appended code,
    fill and padding), and only the patch's own bytes changed."""
    before, after = mff.Update.from_bytes(raw), mff.Update.from_bytes(out)
    if [m.info.filename for m in before.members] != [m.info.filename for m in after.members]:
        raise PatchError("member list changed")
    names = {before.image_name(IMAGES[key][0]): key for key in patch.images()}
    for m in before.members:
        if m.info.filename not in names and after.read(m.info.filename) != m.data:
            raise PatchError(f"{m.info.filename} changed")
    new = {}
    for name, key in names.items():
        base = IMAGES[key][1]
        old_image, new_image = before.read(name), after.read(name)
        old, new[key] = mff.main_payload(old_image), mff.main_payload(new_image)
        if key == "main":
            old = bytes(grown(old, patch))
        if len(new[key]) != len(old):
            raise PatchError(f"{key} image payload is {len(new[key])} bytes, it should be {len(old)}")
        changed = {i for i in range(len(old)) if old[i] != new[key][i]}
        stray = changed - patch.touched(key)
        if stray:
            raise PatchError(f"unexpected change in the {key} image at {base + min(stray):#010x}")
    for hook in patch.hooks:
        if thumb.branch_target(hook.site, new["main"][hook.site - MAIN_BASE :]) != patch.address(hook.symbol):
            raise PatchError(f"hook at {hook.site:#010x} does not reach {hook.symbol}")
    for edit in patch.edits:
        offset = edit.site - IMAGES[edit.image][1]
        if (data := edit.encode()) != new[edit.image][offset : offset + len(data)]:
            raise PatchError(f"edit at {edit.site:#010x} missing")
