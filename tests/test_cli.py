import importlib.metadata
from pathlib import Path

import pytest

from freakpatch.cli import PATCHES, main


def test_list_describes_every_patch(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines] == list(PATCHES)
    assert all(len(line.split()) > 1 for line in lines)


def test_version_matches_the_package(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_:
        main(["--version"])
    assert exit_.value.code == 0
    assert capsys.readouterr().out.strip() == f"freakpatch {importlib.metadata.version('freakpatch')}"


def test_missing_firmware_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_:
        main([str(tmp_path / "nope.mff")])
    assert exit_.value.code == 2


def test_other_files_are_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    other = tmp_path / "other.mff"
    other.write_bytes(b"not firmware")
    assert main([str(other)]) == 1
    assert "not the official" in capsys.readouterr().err
    assert not (tmp_path / "other_release.mff").exists()


def test_default_output_sits_next_to_the_input(tmp_path: Path, stock_mff: bytes, patched_mff: bytes) -> None:
    official = tmp_path / "microfreak.mff"
    official.write_bytes(stock_mff)
    assert main([str(official)]) == 0
    assert (tmp_path / "microfreak_release.mff").read_bytes() == patched_mff
