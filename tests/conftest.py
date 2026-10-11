"""Fixtures for tests that need the official firmware file.

The patcher ships no firmware, so these tests read your own copy: set
``FREAKPATCH_STOCK_MFF`` to the official 5.0.0.2084 ``.mff``, or keep the copy
MIDI Control Center installs on macOS. Without it they are skipped.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from freakpatch import mff
from freakpatch.patcher import LATEST_SHA256, Patch, apply

_MCC_COPY = Path("/Library/Arturia/MIDI Control Center/Firmware/microfreak_Firmware_Update_5.0.0.2084.mff")


@pytest.fixture(scope="session")
def stock_mff() -> bytes:
    path = Path(os.environ.get("FREAKPATCH_STOCK_MFF", _MCC_COPY))
    if not path.is_file():
        pytest.skip("official firmware file not available (set FREAKPATCH_STOCK_MFF)")
    raw = path.read_bytes()
    import hashlib

    if hashlib.sha256(raw).hexdigest() != LATEST_SHA256:
        pytest.skip(f"{path} is not the official 5.0.0.2084 file")
    return raw


@pytest.fixture(scope="session")
def release_patch() -> Patch:
    return Patch.load("release")


@pytest.fixture(scope="session")
def patched_mff(stock_mff: bytes, release_patch: Patch) -> bytes:
    return apply(stock_mff, release_patch)


@pytest.fixture(scope="session")
def stock_payload(stock_mff: bytes) -> bytes:
    update = mff.Update.from_bytes(stock_mff)
    return mff.main_payload(update.read(update.main_name))


@pytest.fixture(scope="session")
def patched_payload(patched_mff: bytes) -> bytes:
    update = mff.Update.from_bytes(patched_mff)
    return mff.main_payload(update.read(update.main_name))
