import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from build_patch import build, combine  # noqa: E402

SHIPPED = sorted((ROOT / "src/freakpatch/patches").glob("*.json"))


def _without_source_hashes(patch: dict) -> dict:
    """Code, symbols, hooks, edits and options; not the hash of the source text, which comments also change."""
    out = {k: v for k, v in patch.items() if k != "source_sha256"}
    if "parts" in out:
        out["parts"] = [{k: v for k, v in p.items() if k != "source_sha256"} for p in out["parts"]]
    return out


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang not installed")
@pytest.mark.parametrize("path", SHIPPED, ids=[p.stem for p in SHIPPED])
def test_shipped_patch_matches_source(path: Path) -> None:
    """Every shipped JSON is what tools/build_patch.py builds now, including a combined build's hooks and edits."""
    shipped = json.loads(path.read_text())
    spec = json.loads((ROOT / "patches" / f"{path.stem}.hooks.json").read_text())
    if "combine" in spec:
        built = combine(spec, [build(ROOT / "patches" / name) for name in spec["combine"]])
    else:
        built = build(ROOT / "patches" / path.stem)
    assert _without_source_hashes(built) == _without_source_hashes(shipped)
