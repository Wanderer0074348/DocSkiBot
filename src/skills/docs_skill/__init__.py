from .documents import WriteDocumentTool, ReadDocumentTool, ListDocumentsTool
from .diary import AppendDiaryTool
from .gdocs import CreateGoogleDocTool, ReadGoogleDocTool, AppendGoogleDocTool, OverwriteGoogleDocTool
from .gdrive import DeleteGoogleDocTool, ListGoogleDocsTool

TOOLS = [
    # Local workspace docs
    WriteDocumentTool(),
    ReadDocumentTool(),
    ListDocumentsTool(),
    # Google Docs — diary shortcut
    AppendDiaryTool(),
    # Google Docs — content operations (Docs API)
    CreateGoogleDocTool(),
    ReadGoogleDocTool(),
    AppendGoogleDocTool(),
    OverwriteGoogleDocTool(),
    # Google Drive — file management (Drive API)
    DeleteGoogleDocTool(),
    ListGoogleDocsTool(),
]

__all__ = ["TOOLS"]
