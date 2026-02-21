from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool


class FormField(BaseModel):
    label: str = Field(description="Label shown next to the input (max 45 chars)")
    placeholder: str = Field(default="", description="Hint text inside the field (max 100 chars)")
    long: bool = Field(default=False, description="True for a multi-line text area (e.g. document body), False for a single-line input")


class RequestFormInput(BaseModel):
    title: str = Field(description="Title shown at the top of the form dialog (max 45 chars)")
    fields: list[FormField] = Field(description="Fields to collect from the user, 1–5 items max")


# Single-user bot — one pending form at a time is sufficient.
_pending_form: dict | None = None


def store_pending_form(form: dict) -> None:
    global _pending_form
    _pending_form = form


def pop_pending_form() -> dict | None:
    global _pending_form
    form, _pending_form = _pending_form, None
    return form


class RequestFormTool(BaseTool):
    name: str = "request_form"
    description: str = (
        "Send the user a Discord modal form to collect structured input. "
        "Use when you need several pieces of information at once — e.g. a document title and its body. "
        "Supports up to 5 fields. Set long=True for multi-line fields (document content, descriptions). "
        "After calling this tool, end your message by telling the user to click 'Open Form'."
    )
    args_schema: type[BaseModel] = RequestFormInput

    def _run(
        self,
        title: str,
        fields: list[FormField],
        run_manager: Optional[object] = None,
    ) -> str:
        store_pending_form({
            "title": title[:45],
            "fields": [
                {
                    "label": f.label[:45],
                    "placeholder": f.placeholder[:100],
                    "long": f.long,
                }
                for f in fields[:5]
            ],
        })
        return f"Form '{title}' queued — the user will see an Open Form button."

    async def _arun(
        self,
        title: str,
        fields: list[FormField],
        run_manager: Optional[object] = None,
    ) -> str:
        return self._run(title, fields)
