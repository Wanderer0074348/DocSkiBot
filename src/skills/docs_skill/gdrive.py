import asyncio
from typing import Optional

from ... import auth
from .base import WorkspaceTool
from .gdocs import DocIdInput


def _delete_doc(doc_id: str) -> None:
    drive = auth.get_drive_service(auth.current_user_id.get())
    drive.files().delete(fileId=doc_id).execute()


def _list_docs() -> str:
    drive = auth.get_drive_service(auth.current_user_id.get())
    results = drive.files().list(
        q="mimeType='application/vnd.google-apps.document' and trashed=false",
        fields="files(id, name, modifiedTime)",
        orderBy="modifiedTime desc",
        pageSize=20,
    ).execute()
    files = results.get("files", [])
    if not files:
        return "No Google Docs found."
    lines = [
        f"- {f['name']} (ID: {f['id']}, modified: {f['modifiedTime'][:10]})"
        for f in files
    ]
    return "Google Docs:\n" + "\n".join(lines)


# ── Tools ─────────────────────────────────────────────────────────────────────

class DeleteGoogleDocTool(WorkspaceTool):
    name: str = "delete_google_doc"
    description: str = (
        "Permanently delete a Google Doc by its document ID. "
        "ALWAYS ask the user to confirm by document name before calling this — deletion cannot be undone."
    )
    args_schema: type[DocIdInput] = DocIdInput

    def _run(self, doc_id: str, run_manager: Optional[object] = None) -> str:
        _delete_doc(doc_id)
        return f"Doc {doc_id} permanently deleted."

    async def _arun(self, doc_id: str, run_manager: Optional[object] = None) -> str:
        await asyncio.to_thread(_delete_doc, doc_id)
        return f"Doc {doc_id} permanently deleted."


class ListGoogleDocsTool(WorkspaceTool):
    name: str = "list_google_docs"
    description: str = (
        "List all Google Docs in the user's Drive with names, IDs, and last-modified dates. "
        "Prefer show_document_picker for interactive selection — use this only when you need "
        "the list as text (e.g. to summarise what documents exist)."
    )

    def _run(self, run_manager: Optional[object] = None) -> str:
        return _list_docs()

    async def _arun(self, run_manager: Optional[object] = None) -> str:
        return await asyncio.to_thread(_list_docs)
