from pathlib import Path

import pytest

from phoneai.config import load_profile, load_scenario, parse_scenario
from phoneai.tools import known_tools

ROOT = Path(__file__).resolve().parents[2]


def test_parse_scenario_substitutes_owner():
    s = parse_scenario(
        "x", "opening: Hi from {owner}\nbrief: Help {owner}\ntools: [save_note]\n", "Sam"
    )
    assert (s.opening, s.brief, s.tools, s.event_minutes) == (
        "Hi from Sam",
        "Help Sam",
        ("save_note",),
        60,
    )


def test_parse_scenario_requires_fields():
    with pytest.raises(ValueError, match="brief"):
        parse_scenario("x", "opening: hi\ntools: []\n", "Sam")


@pytest.mark.parametrize("path", sorted((ROOT / "scenarios" / "examples").glob("*.yaml")))
def test_example_scenarios_are_valid(path: Path):
    s = load_scenario(ROOT / "scenarios", path.stem, "Sam")
    assert set(s.tools) <= known_tools()
    assert "{owner}" not in s.brief + s.opening
    assert s.success_criteria


def test_missing_scenario(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_scenario(tmp_path, "nope", "Sam")


def test_profiles_load():
    p = load_profile(ROOT / "profiles.yaml", "uk_default")
    assert p.record_audio is False
    assert set(p.models()) == {"stt", "llm", "tts"}
    with pytest.raises(KeyError):
        load_profile(ROOT / "profiles.yaml", "nope")
