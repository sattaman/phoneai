"""Contacts from a local, gitignored YAML file. Phone numbers live only here."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from phoneai.domain import Contact

E164 = re.compile(r"^\+[1-9]\d{7,14}$")


class YamlContacts:
    def __init__(self, path: Path) -> None:
        self._path = path

    def _load(self) -> dict[str, Contact]:
        if not self._path.exists():
            return {}
        data = yaml.safe_load(self._path.read_text()) or {}
        contacts = {}
        for cid, raw in data.items():
            phone = str(raw["phone"]).replace(" ", "")
            if not E164.match(phone):
                raise ValueError(f"contact {cid!r}: phone must be E.164, e.g. +447700900123")
            contacts[cid] = Contact(
                id=cid,
                name=raw.get("name", cid),
                phone=phone,
                relationship=raw.get("relationship", ""),
            )
        return contacts

    def get(self, contact_id: str) -> Contact:
        return self._load()[contact_id]

    def ids(self) -> list[str]:
        return sorted(self._load())
