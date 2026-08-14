"""Plain-text run feedback: stage banners, timers, progress bars, spinners, key/value facts."""
import contextlib
import subprocess
import sys
import time

from tqdm import tqdm

_RULE = "=" * 78


def banner(title: str) -> None:
    print(f"\n{_RULE}\n{title}\n{_RULE}", flush=True)


def kv(label: str, value) -> None:
    print(f"  {label}: {value}", flush=True)


def step(msg: str) -> None:
    print(f"  -> {msg}", flush=True)


@contextlib.contextmanager
def stage(name: str):
    banner(name)
    t0 = time.time()
    try:
        yield
    finally:
        print(f"  [done in {time.time() - t0:0.1f}s]", flush=True)


def progress(iterable, desc: str, total=None):
    return tqdm(iterable, desc=f"  {desc}", total=total, ncols=78, file=sys.stdout)

_SPIN_CHILD = (
    "import sys, time, itertools\n"
    "m = sys.argv[1]\n"
    "for c in itertools.cycle('|/-\\\\'):\n"
    "    sys.stdout.write('\\r  -> ' + m + ' ' + c); sys.stdout.flush(); time.sleep(0.1)\n"
)


def spin_start(msg: str):
    """Start a spinner next to msg; return a handle for spin_stop. Animates only on a terminal."""
    handle = {"msg": msg, "t0": time.time(), "proc": None}
    if not sys.stdout.isatty():
        print(f"  -> {msg} ...", flush=True)
        return handle
    try:
        handle["proc"] = subprocess.Popen([sys.executable, "-c", _SPIN_CHILD, msg])
    except Exception:
        print(f"  -> {msg} ...", flush=True)
    return handle


def spin_stop(handle, ok: bool = True):
    """Stop a spinner started with spin_start, printing a done/failed line with the elapsed time."""
    secs = time.time() - handle["t0"]
    status = "done" if ok else "failed"
    proc = handle.get("proc")
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except Exception:
            proc.kill()
        print(f"\r  -> {handle['msg']} {status} ({secs:.1f}s)      ", flush=True)
    else:
        print(f"  -> {handle['msg']} {status} ({secs:.1f}s)", flush=True)


@contextlib.contextmanager
def spinner(msg: str):
    """Live spinner around a blocking step; prints 'done' or 'failed'."""
    handle = spin_start(msg)
    try:
        yield
    except BaseException:
        spin_stop(handle, ok=False)
        raise
    else:
        spin_stop(handle, ok=True)
