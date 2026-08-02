# state.py
from typing import TypedDict, Literal, Optional, Annotated
from pydantic import BaseModel
from langgraph.graph.message import add_messages

class Task(TypedDict):
    id: str
    content: str
    status: Literal["pending", "in_progress", "done"]

class SessionSummary(BaseModel):
    files_touched: list[str]
    decisions_made: list[str]
    current_task_id: Optional[str]
    open_issues: list[str]

class SessionState(TypedDict):
    messages: Annotated[list, add_messages]
    turn_count: int
    task_plan: list[Task]
    edited_files: list[str]
    repo_path: str
    active_branch: str
    session_summary: Optional[SessionSummary]
    _last_write_diff: Optional[dict]
    approved_tool_call_ids: list[str]
    pending_denials: list  # ToolMessages for denied calls, injected into messages by agent node