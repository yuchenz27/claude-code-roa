"""Tests for ROA's core logic and the live permission bracketing.

Runnable two ways (zero dependencies):
    python3 tests/test_core.py     # plain runner
    python3 -m pytest tests/       # if pytest is installed
"""
import os
import sys
import io
import json
import tempfile
import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from roa import core  # noqa: E402

BASE = datetime.datetime(2026, 1, 1, 10, 0, 0)


def at(seconds):
    """An ISO timestamp `seconds` after a fixed base (deterministic tests)."""
    return (BASE + datetime.timedelta(seconds=seconds)).isoformat()


def ev(kind, t, **extra):
    return {"session_id": "s", "cwd": "/x", "hook_event_name": kind,
            "_observed_at": at(t), **extra}


# ---- pure core: apply_event ------------------------------------------------

def test_h2a_pairing():
    st = core.new_state("s", "/x")
    core.apply_event(st, ev("UserPromptSubmit", 0))
    core.apply_event(st, ev("Stop", 90))
    assert st["turns"] == 1
    assert st["h2a_list"] == [90.0]


def test_a2h_prompt_wait():
    st = core.new_state("s", "/x")
    core.apply_event(st, ev("UserPromptSubmit", 0))
    core.apply_event(st, ev("Stop", 60))
    core.apply_event(st, ev("UserPromptSubmit", 200))  # 140s prompt wait
    assert st["a2h_list"] == [140.0]


def test_permission_excluded_from_h2a():
    # 120s wall-clock turn with 30s of it spent waiting on a permission prompt.
    st = core.new_state("s", "/x")
    core.apply_event(st, ev("UserPromptSubmit", 0))
    core.apply_event(st, ev("Stop", 120, _perm_s=30.0, _perm_n=1))
    assert st["h2a_list"] == [90.0]          # 120 - 30 permission
    assert st["perm_total_s"] == 30.0
    assert st["perm_count"] == 1


def test_token_delta_accumulates():
    st = core.new_state("s", "/x")
    core.apply_event(st, ev("UserPromptSubmit", 0))
    core.apply_event(st, ev("Stop", 10, _out_tokens=100, _total_tokens=5000))
    core.apply_event(st, ev("UserPromptSubmit", 20))
    core.apply_event(st, ev("Stop", 30, _out_tokens=50, _total_tokens=4000))
    assert st["out_tokens"] == 150
    assert st["total_tokens"] == 9000


def test_double_submit_keeps_latest_start():
    # submit, submit again (edited), then stop -> H2A measured from 2nd submit
    st = core.new_state("s", "/x")
    core.apply_event(st, ev("UserPromptSubmit", 0))
    core.apply_event(st, ev("UserPromptSubmit", 40))
    core.apply_event(st, ev("Stop", 100))
    assert st["h2a_list"] == [60.0]          # 100 - 40, not 100 - 0


def test_formatters():
    assert core.fmt(45) == "45s"
    assert core.fmt(90) == "1m30s"
    assert core.fmt(3700) == "1h01m"
    assert core.ftok(950) == "950"
    assert core.ftok(2500) == "2k"
    assert core.ftok(1_500_000) == "1.5M"


def test_is_perm_notification():
    assert core.is_perm_notification({"message": "Claude needs your permission to use Bash"})
    assert not core.is_perm_notification({"message": "Claude is waiting for your input"})
    assert not core.is_perm_notification({})


# ---- integration: live permission bracketing through tracker.main ----------

def _fire(tracker, kind, t, **extra):
    """Drive the real hook entrypoint for one event (fresh-process semantics)."""
    payload = {"session_id": "s", "cwd": "/x", "hook_event_name": kind, **extra}
    # tracker.main stamps its own _observed_at from datetime.now(); override it
    # deterministically by freezing now() for the duration of the call.
    import roa.tracker as tr
    real_dt = tr.datetime

    class _FrozenDateTime(real_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return real_dt.datetime.fromisoformat(at(t))

    tr.datetime = type("dt", (), {"datetime": _FrozenDateTime})
    old_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO(json.dumps(payload))
        tracker.main()
    finally:
        sys.stdin = old_stdin
        tr.datetime = real_dt


def test_permission_bracket_end_to_end():
    import roa.tracker as tracker
    with tempfile.TemporaryDirectory() as d:
        os.environ["ROA_DIR"] = d
        try:
            # submit@0 -> permission prompt@30 -> approved (PostToolUse)@90 -> stop@120
            _fire(tracker, "UserPromptSubmit", 0)
            _fire(tracker, "Notification", 30,
                  message="Claude needs your permission to use Bash")
            _fire(tracker, "PostToolUse", 90)
            _fire(tracker, "Stop", 120)
            st = json.load(open(os.path.join(d, "state", "s.json")))
            assert st["h2a_list"] == [60.0]       # 120 - 60s permission
            assert st["perm_total_s"] == 60.0
            assert st["perm_count"] == 1
        finally:
            del os.environ["ROA_DIR"]


def test_idle_notification_is_not_permission():
    import roa.tracker as tracker
    with tempfile.TemporaryDirectory() as d:
        os.environ["ROA_DIR"] = d
        try:
            _fire(tracker, "UserPromptSubmit", 0)
            _fire(tracker, "Notification", 20,
                  message="Claude is waiting for your input")  # idle, not permission
            _fire(tracker, "Stop", 50)
            st = json.load(open(os.path.join(d, "state", "s.json")))
            assert st["h2a_list"] == [50.0]       # nothing carved out
            assert st["perm_count"] == 0
        finally:
            del os.environ["ROA_DIR"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERR  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
