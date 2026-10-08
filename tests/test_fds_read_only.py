"""The fds_read_only mirror of external FDS output (#669)."""

import os

import pytest


@pytest.fixture
def fds_output(tmp_path):
    src = tmp_path / "case"
    (src / "sub").mkdir(parents=True)
    (src / "case.smv").write_text("CHID\ncase\n")
    (src / "case_1_1.sf").write_bytes(b"slice")
    (src / "sub" / "case_devc.csv").write_text("s,C\n")
    (src / "case.pickle").write_bytes(b"cache")
    return src


def _state(root):
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def _check_mirror(src, mirror, before):
    assert not (mirror / "case.pickle").exists()
    assert not (mirror / "case.smv").is_symlink()
    for name in ("case.smv", "case_1_1.sf", "sub/case_devc.csv"):
        assert (mirror / name).read_bytes() == (src / name).read_bytes()
    assert _state(src) == before


def test_mirror_links_the_data_and_copies_the_smv(fds_read_only, fds_output):
    before = _state(fds_output)
    mirror = fds_read_only(fds_output)
    _check_mirror(fds_output, mirror, before)
    assert (mirror / "case_1_1.sf").is_symlink()
    assert fds_read_only(fds_output) == mirror


def test_mirror_copies_when_symlinks_are_denied(fds_read_only, fds_output, monkeypatch):
    """Windows without symlink privilege raises OSError (WinError 1314)."""

    def denied(src, dst, *args, **kwargs):
        raise OSError(1314, "A required privilege is not held by the client")

    monkeypatch.setattr(os, "symlink", denied)
    before = _state(fds_output)
    mirror = fds_read_only(fds_output)
    _check_mirror(fds_output, mirror, before)
    for name in ("case_1_1.sf", "sub/case_devc.csv"):
        assert not (mirror / name).is_symlink()
        assert not os.path.samefile(fds_output / name, mirror / name)


@pytest.mark.skipif(
    "PYTEST_XDIST_WORKER" not in os.environ, reason="needs an xdist worker"
)
def test_an_xdist_worker_keeps_the_fdsreader_cache_out_of_the_case(tmp_path):
    """Under xdist, fdsreader's pickle goes to the worker's folder (conftest)."""
    from fdsreader.simulation import Simulation

    case = tmp_path / "case"
    case.mkdir()
    pickle = os.path.abspath(Simulation._get_pickle_filename(str(case), "case"))
    assert os.path.basename(pickle) == "case.pickle"
    assert os.path.commonpath([pickle, str(case)]) != str(case)
