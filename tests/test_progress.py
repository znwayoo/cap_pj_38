import io
from contextlib import redirect_stdout

from src import progress


def test_banner_prints_title():
    buf = io.StringIO()
    with redirect_stdout(buf):
        progress.banner("HELLO STAGE")
    out = buf.getvalue()
    assert "HELLO STAGE" in out and "=" * 20 in out


def test_kv_and_step():
    buf = io.StringIO()
    with redirect_stdout(buf):
        progress.kv("rows", 1234)
        progress.step("harmonising")
    out = buf.getvalue()
    assert "rows: 1234" in out and "harmonising" in out


def test_stage_prints_timing():
    buf = io.StringIO()
    with redirect_stdout(buf):
        with progress.stage("STAGE X"):
            pass
    out = buf.getvalue()
    assert "STAGE X" in out and "done in" in out


def test_progress_iterates_fully():
    buf = io.StringIO()
    with redirect_stdout(buf):
        seen = list(progress.progress(range(5), desc="loop", total=5))
    assert seen == [0, 1, 2, 3, 4]
