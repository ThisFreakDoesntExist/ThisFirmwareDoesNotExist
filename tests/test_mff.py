import io
import zipfile

import pytest

from freakpatch import mff


def _update(payload: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        z.writestr("info.json", b'{"version_number": "test"}')
        z.writestr("nanowave_main__test.bin", mff.build_image(bytes(0x40), payload))
        z.writestr("nanowave_iochip_oled__test.bin", b"\x01" * 0x50)
    return out.getvalue()


def test_checksum_round_trip() -> None:
    image = mff.build_image(bytes(0x40), b"\x12\x34\x56")
    assert image[1] == image[-1] == 0x12 ^ 0x34 ^ 0x56
    assert mff.xor8(image[0x40:]) == 0
    assert mff.main_payload(image) == b"\x12\x34\x56"


def test_bad_checksum_rejected() -> None:
    image = bytearray(mff.build_image(bytes(0x40), b"\x12\x34\x56"))
    image[0x41] ^= 1
    with pytest.raises(ValueError):
        mff.main_payload(bytes(image))


def test_update_rewrite_keeps_members_and_order() -> None:
    update = mff.Update.from_bytes(_update(b"abc"))
    assert update.main_name == "nanowave_main__test.bin"
    changed = update.with_member(update.main_name, mff.build_image(bytes(0x40), b"abcd"))
    again = mff.Update.from_bytes(changed.to_bytes())
    assert [m.info.filename for m in again.members] == [m.info.filename for m in update.members]
    assert mff.main_payload(again.read(again.main_name)) == b"abcd"
    assert again.read("info.json") == update.read("info.json")
    with zipfile.ZipFile(io.BytesIO(changed.to_bytes())) as z:
        assert z.testzip() is None
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
