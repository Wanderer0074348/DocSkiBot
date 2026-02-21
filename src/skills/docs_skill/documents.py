import aiofiles
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun

from .base import WorkspaceTool


class WriteDocumentInput(BaseModel):
    filename: str = Field(description="Filename with underscores, no extension. E.g. 'prof_task_summary'")
    content: str = Field(description="Full text content to write")


class ReadDocumentInput(BaseModel):
    filename: str = Field(description="Filename without extension. Use list_documents if unsure of exact name")


class WriteDocumentTool(WorkspaceTool):
    name: str = "write_document"
    description: str = (
        "Write text content to a file in the agent workspace. "
        "Use for documents, notes, drafts, summaries, or any text to save locally."
    )
    args_schema: type[BaseModel] = WriteDocumentInput

    def _sanitize(self, name: str) -> str:
        return name.replace(" ", "_").replace("/", "_").replace("..", "_")

    def _run(self, filename: str, content: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        filepath = self.workspace / f"{self._sanitize(filename)}.txt"
        filepath.write_text(content, encoding="utf-8")
        return f"Saved to {filepath.name}"

    async def _arun(self, filename: str, content: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        filepath = self.workspace / f"{self._sanitize(filename)}.txt"
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(content)
        return f"Saved to {filepath.name}"


class ReadDocumentTool(WorkspaceTool):
    name: str = "read_document"
    description: str = (
        "Read the contents of a previously saved local document. "
        "Use when the user wants to recall or continue working on saved text."
    )
    args_schema: type[BaseModel] = ReadDocumentInput

    def _sanitize(self, name: str) -> str:
        return name.replace(" ", "_").replace("/", "_").replace("..", "_")

    def _run(self, filename: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        safe = self._sanitize(filename)
        for candidate in [self.workspace / safe, self.workspace / f"{safe}.txt"]:
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")
        return f"'{filename}' not found. Run list_documents first."

    async def _arun(self, filename: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        safe = self._sanitize(filename)
        for candidate in [self.workspace / safe, self.workspace / f"{safe}.txt"]:
            if candidate.exists():
                async with aiofiles.open(candidate, "r", encoding="utf-8") as f:
                    return await f.read()
        return f"'{filename}' not found. Run list_documents first."


class ListDocumentsTool(WorkspaceTool):
    name: str = "list_documents"
    description: str = (
        "List all locally saved documents in the agent workspace. "
        "Use before reading a file to confirm its exact name."
    )

    def _run(self, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        files = sorted(f for f in self.workspace.iterdir() if f.is_file())
        if not files:
            return "No local documents saved yet."
        return "Saved files:\n" + "\n".join(f"- {f.name} ({f.stat().st_size} bytes)" for f in files)

    async def _arun(self, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        return self._run()
