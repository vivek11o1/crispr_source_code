# tasks.py
from states import SessionState, Task
from typing import Literal, Annotated
from langgraph.prebuilt import InjectedState

def manage_tasks(
    action: Literal["create", "update_status", "list"],
    tasks: list[str] | None = None,
    task_id: str | None = None,
    status: Literal["pending", "in_progress", "done"] | None = None,
    state: Annotated[SessionState, InjectedState] = None,
) -> tuple[str, dict]:
    """Create, update status, or list tasks in the session task plan."""

    current: list[Task] = state["task_plan"]

    if action == "create":
        new_tasks: list[Task] = [
            {"id": str(i + 1), "content": t, "status": "pending"}
            for i, t in enumerate(tasks)
        ]
        return f"Created {len(new_tasks)} tasks.", {"task_plan": new_tasks}

    if action == "update_status":
        updated: list[Task] = [
            {**t, "status": status} if t["id"] == task_id else t
            for t in current
        ]
        return f"Task {task_id} -> {status}", {"task_plan": updated}

    if action == "list":
        summary = "\n".join(f"[{t['status']}] {t['id']}: {t['content']}" for t in current)
        return summary or "No tasks yet.", {}

    return f"Unknown action: {action}", {}