import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from build_patch import assemble  # noqa: E402


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang not installed")
def test_shipped_patch_matches_source() -> None:
    shipped = json.loads((ROOT / "src/freakpatch/patches/release.json").read_text())
    code, symbols = assemble(ROOT / "patches/release.S")
    assert code.hex() == shipped["code"]
    assert {k: symbols[k] for k in shipped["symbols"]} == shipped["symbols"]
