from __future__ import annotations

from phoneai.tools import Tool, ToolDeps


def build(deps: ToolDeps) -> Tool:
    async def save_note(note: str) -> str:
        """Save a note for the owner: a message, preference or request from the caller.

        Args:
            note: One short factual sentence, or their message word for word.
        """
        if note.strip():
            deps.state.notes.append(note.strip())
        return "Saved."

    return save_note
