import os
import asyncio
from datetime import datetime
from pydantic import BaseModel, Field

from .base import WorkspaceTool
from .gdocs import _append_to_doc


class AppendDiaryInput(BaseModel):
    entry: str = Field(description="The diary entry text. Timestamps and formatting are handled automatically.")


class AppendDiaryTool(WorkspaceTool):
    name: str = "append_diary"
    description: str = (
        "Add a timestamped entry to the diary Google Doc. "
        "Use when the user shares something that happened, wants to log their day, "
        "record a thought, or journal anything."
    )
    args_schema: type[BaseModel] = AppendDiaryInput
    doc_id: str = ""

    def model_post_init(self, __context: object) -> None:
        self.doc_id = os.environ.get("GOOGLE_DIARY_DOC_ID", "")

    def _format_text(self, entry: str) -> str:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"\n[{stamp}]\n{entry}\n"

    def _run(self, entry: str) -> str:
        if not self.doc_id:
            return "No diary doc configured. Set GOOGLE_DIARY_DOC_ID in .env, or use append_google_doc with a specific doc."
        _append_to_doc(self.doc_id, self._format_text(entry))
        return f"Diary entry added at {datetime.now().strftime('%H:%M')}"

    async def _arun(self, entry: str) -> str:
        if not self.doc_id:
            return "No diary doc configured. Set GOOGLE_DIARY_DOC_ID in .env, or use append_google_doc with a specific doc."
        await asyncio.to_thread(_append_to_doc, self.doc_id, self._format_text(entry))
        return f"Diary entry added at {datetime.now().strftime('%H:%M')}"
