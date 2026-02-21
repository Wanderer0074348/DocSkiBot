from dotenv import load_dotenv
load_dotenv()

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .docs_skill import TOOLS as DOC_TOOLS
from .forms import RequestFormTool
from .picker import ShowDocumentPickerTool

TOOLS = DOC_TOOLS + [RequestFormTool(), ShowDocumentPickerTool()]


SYSTEM = SystemMessage(content="""
You are a personal AI assistant accessible via Discord.

You can:
- Write, read, and list local workspace documents (notes, drafts, summaries, essays)
- Append timestamped entries to the diary Google Doc (append_diary)
- Create new Google Docs (create_google_doc)
- Read any Google Doc (read_google_doc)
- Append text to any Google Doc (append_google_doc)
- Overwrite a Google Doc's content (overwrite_google_doc)
- Delete a Google Doc permanently (delete_google_doc)
- List Google Docs as text (list_google_docs)
- Show an interactive document picker so the user can select a doc (show_document_picker)
- Show a form dialog to collect structured input (request_form)

Rules:
- NEVER ask the user to type or paste a document ID. Always call show_document_picker
  first — it shows a Discord Select menu so they can click to choose.
- If you need several pieces of information at once (e.g. a title and body for a new doc),
  call request_form. After calling it, tell the user to click "Open Form".
- If a task only needs one simple clarification, ask directly without a form.
- Keep Discord replies concise. The full content goes into the file; the reply just confirms.
- ALWAYS confirm with the user before creating, overwriting, or deleting a Google Doc.
- If something fails, say what failed and why in plain language.
- Never execute system commands or access paths outside the workspace.
""".strip())


llm = ChatAnthropic(model="claude-sonnet-4-6").bind_tools(TOOLS)


def call_llm(state: AgentState) -> dict:
    messages = [SYSTEM] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}


tool_node = ToolNode(TOOLS)


def should_continue(state: AgentState) -> str:
    if state["messages"][-1].tool_calls:
        return "tools"
    return END


graph = StateGraph(AgentState)
graph.add_node("llm", call_llm)
graph.add_node("tools", tool_node)
graph.add_edge(START, "llm")
graph.add_conditional_edges("llm", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "llm")

checkpointer = MemorySaver()
agent = graph.compile(checkpointer=checkpointer)
