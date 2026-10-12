import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from build_patch import assemble  # noqa: E402

SHIPPED = sorted((ROOT / "src/freakpatch/patches").glob("*.json"))


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang not installed")
@pytest.mark.parametrize("path", SHIPPED, ids=[p.stem for p in SHIPPED])
def test_shipped_patch_matches_source(path: Path) -> None:
    shipped = json.loads(path.read_text())
    for part in shipped.get("parts", [shipped]):
        spec = json.loads((ROOT / "patches" / f"{part['name']}.hooks.json").read_text())
        code, symbols = assemble(ROOT / "patches" / spec.get("source", f"{part['name']}.S"))
        assert code.hex() == part["code"]
        assert {k: symbols[k] for k in part["symbols"]} == part["symbols"]
