import json
from pathlib import Path

import pytest

from phoneai.adapters.contacts_yaml import YamlContacts
from phoneai.adapters.telephony_livekit import CallRequest


def test_contacts_load_and_validate(tmp_path: Path):
    f = tmp_path / "c.yaml"
    f.write_text('friend:\n  name: A Friend\n  phone: "+44 7700 900001"\n')
    c = YamlContacts(f).get("friend")
    assert (c.name, c.phone) == ("A Friend", "+447700900001")

    f.write_text('bad:\n  phone: "07700900001"\n')
    with pytest.raises(ValueError, match=r"E\.164"):
        YamlContacts(f).get("bad")


def test_missing_contacts_file_is_empty(tmp_path: Path):
    contacts = YamlContacts(tmp_path / "none.yaml")
    assert contacts.ids() == []
    with pytest.raises(KeyError):
        contacts.get("x")


def test_call_request_metadata_has_no_phone_number():
    req = CallRequest(
        call_id="c1", contact_id="friend", scenario="s", profile="p", dispatched_at=1000.0
    )
    meta = json.loads(req.to_metadata())
    assert meta == {
        "call_id": "c1",
        "contact_id": "friend",
        "scenario": "s",
        "profile": "p",
        "dispatched_at": 1000.0,
    }
    assert CallRequest.from_metadata(req.to_metadata(), "d", "d") == req


def test_call_request_defaults_for_browser_sessions():
    req = CallRequest.from_metadata(None, "book_gym_session", "uk_default")
    assert (req.contact_id, req.scenario, req.profile) == (None, "book_gym_session", "uk_default")
