import importlib

import pytest

import config
import prepare_data


@pytest.fixture(autouse=True)
def _restore_config_after():
    # Restore the real config module state after tests that reload it with a patched DATA_DIR.
    yield
    importlib.reload(config)
    importlib.reload(prepare_data)


def _reload(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    importlib.reload(config)
    importlib.reload(prepare_data)
    return prepare_data


def test_validate_false_when_empty(tmp_path, monkeypatch):
    pd = _reload(tmp_path, monkeypatch)
    assert pd.validate() is False


def test_standardise_moves_dropped_file_to_canonical_path(tmp_path, monkeypatch):
    pd = _reload(tmp_path, monkeypatch)
    drop = tmp_path / "downloads" / "middlesex"
    drop.mkdir(parents=True)
    (drop / "whatever_the_publisher_named_it.csv").write_text("depth,ratio\n0,0\n1,0.2\n")
    problems = pd.standardise()
    assert problems == []
    assert (tmp_path / "curves" / "middlesex.csv").exists()


def test_standardise_flags_ambiguous_drop(tmp_path, monkeypatch):
    pd = _reload(tmp_path, monkeypatch)
    drop = tmp_path / "downloads" / "middlesex"
    drop.mkdir(parents=True)
    (drop / "a.csv").write_text("x")
    (drop / "b.csv").write_text("y")
    # two candidate files for one dataset must be flagged, not silently picked
    problems = pd.standardise()
    assert any("middlesex" in p for p in problems)
    assert not (tmp_path / "curves" / "middlesex.csv").exists()
