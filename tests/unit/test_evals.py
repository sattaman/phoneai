from datetime import date, time
from pathlib import Path

from phoneai.domain import Arrangement, ArrangementStatus, CallState
from phoneai.evals import EvalCase, EvalRow, check_expectations, load_cases, render_report
from tests.conftest import TZ, at

ROOT = Path(__file__).resolve().parents[2]


def state(status=ArrangementStatus.PROVISIONAL, start=time(15), place="PureGym Leeds", notes=()):
    return CallState(
        notes=list(notes), arrangement=Arrangement(date(2026, 10, 4), start, place, status)
    )


CASE = EvalCase(
    "c",
    "unknown",
    ("hi",),
    {
        "status": "provisional",
        "start": "15:00",
        "place": "puregym",
        "note": "quid",
        "must_not_say": ["busy"],
    },
)


def test_cases_file_is_valid():
    cases = load_cases(ROOT / "evals" / "cases.yaml")
    assert len({c.id for c in cases}) == len(cases) >= 5
    for c in cases:
        c.make_calendar(TZ)


def test_busy_calendar_from_case():
    cal = EvalCase("c", [["2026-10-04 14:00", "2026-10-04 16:00"]], (), {}).make_calendar(TZ)
    assert cal.events == [(at(4, 14), at(4, 16))]


def test_check_expectations_pass_and_fail():
    assert check_expectations(CASE, state(notes=["owes twenty quid"]), "lovely") == []
    failures = check_expectations(
        CASE, state(ArrangementStatus.AGREED, time(16), "Gym Group"), "he's busy"
    )
    assert any("status" in f for f in failures)
    assert any("start" in f for f in failures)
    assert any("place" in f for f in failures)
    assert any("note" in f for f in failures)
    assert any("busy" in f for f in failures)
    assert check_expectations(CASE, CallState(), "")[0] == "nothing recorded"


def test_render_report():
    row = EvalRow("m", "c", 0, True, [], 2, 2, 0.5, 1000.0, 100.0)
    bad = EvalRow("m", "d", 0, False, ["nothing recorded"], 1, 2, 0.7, 1000.0, 100.0)
    md = render_report([row, bad], {"m": (1e-6, 2e-6)})
    assert "| `m` | 2 | 50% | 75% | 0.60s | 1,000 / 100 | $0.0012 |" in md
    assert "d #0: nothing recorded" in md
