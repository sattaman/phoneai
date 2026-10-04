"""Settings (from env / .env), voice profiles and scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from phoneai.domain import Scenario, WorkingHours

ROOT = Path.cwd()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    owner_name: str = "Tom"
    timezone: str = "Europe/London"
    max_call_seconds: int = 300
    ringing_timeout_seconds: int = 30
    available_from: time = time(9, 0)  # hours the owner can be booked
    available_until: time = time(18, 0)

    openrouter_api_key: str = Field(
        default="", validation_alias=AliasChoices("OPENROUTER_API_KEY", "OPEN_ROUTER_API_SECRET")
    )
    summary_model: str = "google/gemini-2.5-flash-lite"

    sip_domain: str = Field(default="", validation_alias="TWILIO_SIP_DOMAIN")
    sip_username: str = Field(default="", validation_alias="TWILIO_SIP_USERNAME")
    sip_password: str = Field(default="", validation_alias="TWILIO_SIP_PASSWORD")
    caller_id: str = Field(default="", validation_alias="TWILIO_PHONE_NUMBER")

    google_calendar_ical_url: str = ""

    contacts_file: Path = ROOT / "contacts.local.yaml"
    scenarios_dir: Path = ROOT / "scenarios"
    profiles_file: Path = ROOT / "profiles.yaml"
    calls_dir: Path = ROOT / "calls"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def hours(self) -> WorkingHours:
        return WorkingHours(self.available_from, self.available_until)


@dataclass(frozen=True)
class Profile:
    name: str
    stt_model: str
    stt_language: str
    llm_model: str
    llm_fallback: str
    tts_model: str
    tts_voice: str
    tts_language: str
    llm_reasoning_effort: str | None = None  # for reasoning models, e.g. "minimal"
    min_endpointing_delay: float = 0.8
    max_endpointing_delay: float = 3.0
    record_audio: bool = False  # only enable for calls to the owner (privacy)

    def models(self) -> dict[str, str]:
        return {
            "stt": self.stt_model,
            "llm": self.llm_model,
            "tts": f"{self.tts_model}:{self.tts_voice}",
        }


def load_profile(path: Path, name: str) -> Profile:
    data = yaml.safe_load(path.read_text())
    if name not in data:
        raise KeyError(f"profile {name!r} not in {path.name}; have {sorted(data)}")
    return Profile(name=name, **data[name])


def find_scenario(directory: Path, name: str) -> Path:
    """Scenarios live in scenarios/examples (committed) or scenarios/private (gitignored)."""
    for sub in ("private", "examples"):
        path = directory / sub / f"{name}.yaml"
        if path.exists():
            return path
    raise FileNotFoundError(f"scenario {name!r} not found under {directory}/{{private,examples}}")


def parse_scenario(name: str, text: str, owner: str) -> Scenario:
    data = yaml.safe_load(text.replace("{owner}", owner))
    missing = {"brief", "opening", "tools"} - data.keys()
    if missing:
        raise ValueError(f"scenario {name!r} missing {sorted(missing)}")
    return Scenario(
        name=name,
        brief=data["brief"].strip(),
        opening=data["opening"].strip(),
        tools=tuple(data["tools"]),
        success_criteria=tuple(data.get("success_criteria", ())),
        event_minutes=int(data.get("event_minutes", 60)),
    )


def load_scenario(directory: Path, name: str, owner: str) -> Scenario:
    return parse_scenario(name, find_scenario(directory, name).read_text(), owner)
