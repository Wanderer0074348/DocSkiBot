"""Document picker tool.

The agent calls show_document_picker() when it needs the user to choose a
Google Doc. This queues a Discord Select menu (via bot.py) rather than
asking the user to type a document ID.
"""

import asyncio
from typing import Optional

from langchain_core.tools import BaseTool

from .. import auth


# Single pending picker per asyncio context — fine for a personal bot.
_pending_picker: list[dict] | None = None


def store_pending_picker(docs: list[dict]) -> None:
    global _pending_picker
    _pending_picker = docs


def pop_pending_picker() -> list[dict] | None:
    global _pending_picker
    docs, _pending_picker = _pending_picker, None
    return docs


class ShowDocumentPickerTool(BaseTool):
    name: str = "show_document_picker"
    description: str = (
        "Show the user a Discord Select menu listing their Google Docs so they can pick one. "
        "Use this any time you need a document ID — never ask the user to type one manually. "
        "After calling this tool, tell the user a document picker will appear below your message."
    )

    def _run(self, run_manager: Optional[object] = None) -> str:
        user_id = auth.current_user_id.get()
        drive = auth.get_drive_service(user_id)
        results = drive.files().list(
            q="mimeType='application/vnd.google-apps.document' and trashed=false",
            fields="files(id, name, modifiedTime)",
            orderBy="modifiedTime desc",
            pageSize=25,
        ).execute()
        docs = results.get("files", [])
        if not docs:
            return "No Google Docs found in the user's Drive."
        store_pending_picker(docs)
        names = "\n".join(f"- {d['name']}" for d in docs)
        return f"Picker queued with {len(docs)} documents:\n{names}"

    async def _arun(self, run_manager: Optional[object] = None) -> str:
        return await asyncio.to_thread(self._run)
