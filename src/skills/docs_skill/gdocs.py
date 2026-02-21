import asyncio
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun

from ... import auth
from .base import WorkspaceTool


def _extract_text(doc: dict) -> str:
    """Extract plain text from a Google Docs document body."""
    text = []
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if paragraph:
            for elem in paragraph.get("elements", []):
                text_run = elem.get("textRun")
                if text_run:
                    text.append(text_run.get("content", ""))
    return "".join(text)


# ── Shared helpers (also imported by diary.py) ────────────────────────────────

def _append_to_doc(doc_id: str, text: str) -> None:
    docs = auth.get_docs_service(auth.current_user_id.get())
    doc = docs.documents().get(documentId=doc_id).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": end_index}, "text": text}}]},
    ).execute()


def _create_doc(title: str, initial_content: str = "") -> str:
    docs = auth.get_docs_service(auth.current_user_id.get())
    doc = docs.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    if initial_content:
        end_index = doc["body"]["content"][-1]["endIndex"] - 1
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": end_index}, "text": initial_content}}]},
        ).execute()
    return doc_id


def _read_doc(doc_id: str) -> str:
    docs = auth.get_docs_service(auth.current_user_id.get())
    doc = docs.documents().get(documentId=doc_id).execute()
    title = doc.get("title", "Untitled")
    return f"# {title}\n\n{_extract_text(doc)}"


def _overwrite_doc(doc_id: str, new_content: str) -> None:
    docs = auth.get_docs_service(auth.current_user_id.get())
    doc = docs.documents().get(documentId=doc_id).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1
    requests = []
    if end_index > 1:
        requests.append({"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index}}})
    requests.append({"insertText": {"location": {"index": 1}, "text": new_content}})
    docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()


# ── Tools ─────────────────────────────────────────────────────────────────────

class CreateGoogleDocInput(BaseModel):
    title: str = Field(description="Title for the new Google Doc")
    initial_content: str = Field(default="", description="Optional initial text content to populate the doc")


class CreateGoogleDocTool(WorkspaceTool):
    name: str = "create_google_doc"
    description: str = (
        "Create a new Google Doc with a given title and optional initial content. "
        "Returns the document ID needed for future operations. "
        "Always confirm the title with the user before creating."
    )
    args_schema: type[BaseModel] = CreateGoogleDocInput

    def _run(self, title: str, initial_content: str = "", run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        doc_id = _create_doc(title, initial_content)
        return f"Created Google Doc '{title}' — ID: {doc_id}"

    async def _arun(self, title: str, initial_content: str = "", run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        doc_id = await asyncio.to_thread(_create_doc, title, initial_content)
        return f"Created Google Doc '{title}' — ID: {doc_id}"


class DocIdInput(BaseModel):
    doc_id: str = Field(description="The Google Doc document ID")


class ReadGoogleDocTool(WorkspaceTool):
    name: str = "read_google_doc"
    description: str = (
        "Read the full text content of a Google Doc by its document ID. "
        "Use show_document_picker first if you don't have the ID."
    )
    args_schema: type[BaseModel] = DocIdInput

    def _run(self, doc_id: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        return _read_doc(doc_id)

    async def _arun(self, doc_id: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        return await asyncio.to_thread(_read_doc, doc_id)


class AppendGoogleDocInput(BaseModel):
    doc_id: str = Field(description="The Google Doc document ID")
    text: str = Field(description="Text to append at the end of the document")


class AppendGoogleDocTool(WorkspaceTool):
    name: str = "append_google_doc"
    description: str = (
        "Append text to the end of an existing Google Doc without touching existing content. "
        "Ideal for adding notes, diary entries, or continuing a document."
    )
    args_schema: type[BaseModel] = AppendGoogleDocInput

    def _run(self, doc_id: str, text: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        _append_to_doc(doc_id, text)
        return f"Text appended to doc {doc_id}."

    async def _arun(self, doc_id: str, text: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        await asyncio.to_thread(_append_to_doc, doc_id, text)
        return f"Text appended to doc {doc_id}."


class OverwriteGoogleDocInput(BaseModel):
    doc_id: str = Field(description="The Google Doc document ID")
    new_content: str = Field(description="New full content — replaces everything currently in the document")


class OverwriteGoogleDocTool(WorkspaceTool):
    name: str = "overwrite_google_doc"
    description: str = (
        "Replace the entire content of an existing Google Doc with new text. "
        "ALWAYS confirm with the user before calling this — it cannot be undone easily."
    )
    args_schema: type[BaseModel] = OverwriteGoogleDocInput

    def _run(self, doc_id: str, new_content: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        _overwrite_doc(doc_id, new_content)
        return f"Doc {doc_id} overwritten successfully."

    async def _arun(self, doc_id: str, new_content: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        await asyncio.to_thread(_overwrite_doc, doc_id, new_content)
        return f"Doc {doc_id} overwritten successfully."
