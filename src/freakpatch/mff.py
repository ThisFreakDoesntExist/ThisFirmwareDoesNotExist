"""MicroFreak ``.mff`` update files: a stored ZIP of ``info.json`` and firmware images.

Every code image is a 64-byte header, the payload, and one trailing byte. Header byte 1
and the trailing byte both hold the XOR of the payload, so all bytes from offset 0x40 to
the end XOR to zero.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, replace
from functools import reduce

HEADER_LEN = 0x40
MAIN_IMAGE_PREFIX = "nanowave_main"


def xor8(data: bytes) -> int:
    return reduce(lambda a, b: a ^ b, data, 0)


@dataclass(frozen=True)
class Member:
    info: zipfile.ZipInfo
    data: bytes


@dataclass(frozen=True)
class Update:
    members: tuple[Member, ...]

    @classmethod
    def from_bytes(cls, raw: bytes) -> Update:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            return cls(tuple(Member(info, z.read(info)) for info in z.infolist()))

    def to_bytes(self) -> bytes:
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
            for m in self.members:
                info = zipfile.ZipInfo(m.info.filename, date_time=m.info.date_time)
                info.external_attr = m.info.external_attr
                info.create_system = m.info.create_system
                z.writestr(info, m.data, compress_type=zipfile.ZIP_STORED)
        return out.getvalue()

    @property
    def main_name(self) -> str:
        names = [m.info.filename for m in self.members if m.info.filename.startswith(MAIN_IMAGE_PREFIX)]
        if len(names) != 1:
            raise ValueError(f"expected one {MAIN_IMAGE_PREFIX}* image, found {len(names)}")
        return names[0]

    def read(self, name: str) -> bytes:
        return next(m.data for m in self.members if m.info.filename == name)

    def with_member(self, name: str, data: bytes) -> Update:
        return Update(tuple(replace(m, data=data) if m.info.filename == name else m for m in self.members))


def main_payload(image: bytes) -> bytes:
    """The code image's payload: header and trailing checksum byte removed."""
    if len(image) < HEADER_LEN + 1 or image[1] != image[-1] or xor8(image[HEADER_LEN:]) != 0:
        raise ValueError("main image checksum is invalid")
    return image[HEADER_LEN:-1]


def build_image(header: bytes, payload: bytes) -> bytes:
    """A code image with a fresh checksum in header byte 1 and the trailing byte."""
    checksum = xor8(payload)
    return header[:1] + bytes([checksum]) + header[2:HEADER_LEN] + payload + bytes([checksum])
