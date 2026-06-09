from __future__ import annotations

import base64
import json
import os
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from app.database import db, now_iso
from agent.prompts import STAGE1_REVIEWER_PROMPT, STAGE2_SUMMARY_PROMPT


class ReviewState(TypedDict):
    job_id: int
    status: Literal["pending", "reviewing", "waiting_for_retry", "all_clear"]
    attempt_count: int
    max_attempts: int
    messages: list[dict]
    room_results: dict[str, bool]
    job: dict | None
    rooms: list[dict]
    photos: list[dict]
    summary: dict | None
    failures: list[dict]


def _load_image_b64(storage_path: str) -> str:
    from app.config import UPLOAD_DIR
    full_path = storage_path
    if not os.path.isabs(full_path):
        full_path = str(UPLOAD_DIR / storage_path)
    with open(full_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _post_agent_message(job_id: int, body: str) -> dict:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO messages (job_id, sender_user_id, sender_type, body, created_at) VALUES (?, NULL, 'agent', ?, ?)",
            (job_id, body, now_iso()),
        )
        msg = conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(msg)


def _post_system_message(job_id: int, body: str) -> dict:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO messages (job_id, sender_user_id, sender_type, body, created_at) VALUES (?, NULL, 'system', ?, ?)",
            (job_id, body, now_iso()),
        )
        msg = conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(msg)


def _build_llm() -> ChatOpenRouter:
    return ChatOpenRouter(
        model=OPENROUTER_MODEL,
        temperature=0,
        openrouter_api_key=OPENROUTER_API_KEY,
    )


def fetch_context(state: ReviewState) -> ReviewState:
    job_id = state["job_id"]
    with db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        job = dict(row) if row else None
        rooms = [dict(r) for r in conn.execute(
            "SELECT * FROM rooms WHERE home_id = ?", (job["home_id"],)
        ).fetchall()] if job else []
        photos = [dict(p) for p in conn.execute(
            "SELECT * FROM photos WHERE job_id = ? ORDER BY sequence", (job_id,)
        ).fetchall()]
        msg_rows = conn.execute(
            "SELECT * FROM messages WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
        messages = [dict(m) for m in msg_rows]

    return {
        **state,
        "job": job,
        "rooms": rooms,
        "photos": photos,
        "messages": messages,
    }


def review_photos(state: ReviewState) -> ReviewState:
    llm = _build_llm()
    job = state["job"]
    rooms = state["rooms"]
    photos = state["photos"]
    job_id = state["job_id"]

    rooms_with_ids = json.dumps([{"id": r["id"], "name": r["name"]} for r in rooms], indent=2)

    stage_1_results: list[dict] = []
    failures: list[dict] = []

    for photo in photos:
        try:
            b64 = _load_image_b64(photo["storage_path"])
        except (FileNotFoundError, IsADirectoryError, OSError):
            stage_1_results.append({
                "photo_id": photo["id"],
                "error": "image_not_found",
                "pass": False,
                "room_id": None,
                "room_name": None,
                "confidence": 0,
                "cleanliness_score": 0,
                "issues": ["Could not load image"],
            })
            continue

        prompt = STAGE1_REVIEWER_PROMPT.format(
            job_id=job_id,
            rooms_with_ids=rooms_with_ids,
            base64_image=b64[:80] + "...",
        )

        msg = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image", "base64": b64, "mime_type": "image/jpeg"},
        ])

        resp = llm.invoke([msg])
        try:
            result = json.loads(resp.content.strip().removeprefix("```json").removesuffix("```").strip())
        except (json.JSONDecodeError, AttributeError):
            result = {
                "photo_id": photo["id"],
                "error": "parse_failed",
                "pass": False,
                "room_id": None,
                "room_name": None,
                "confidence": 0,
                "cleanliness_score": 0,
                "issues": ["Could not parse LLM response"],
            }
        result["photo_id"] = photo["id"]
        stage_1_results.append(result)

    summary_prompt = STAGE2_SUMMARY_PROMPT.format(
        job_id=job_id,
        rooms_with_ids=rooms_with_ids,
        stage_1_results=json.dumps(stage_1_results, indent=2),
    )

    summary_resp = llm.invoke([SystemMessage(content=summary_prompt)])
    try:
        summary = json.loads(summary_resp.content.strip().removeprefix("```json").removesuffix("```").strip())
    except (json.JSONDecodeError, AttributeError):
        summary = {
            "room_assignments": [],
            "overall_pass": False,
            "retake_needed": [],
            "summary": "Could not parse summary response.",
        }

    with db() as conn:
        for assignment in summary.get("room_assignments", []):
            conn.execute(
                """UPDATE photos SET room_id = ?, review_status = ?, review_notes = ?
                   WHERE id = ? AND job_id = ?""",
                (
                    assignment.get("room_id"),
                    assignment.get("review_status", "failed"),
                    assignment.get("review_notes"),
                    assignment["photo_id"],
                    job_id,
                ),
            )
        conn.commit()

    overall_pass = summary.get("overall_pass", False)
    retake_list = summary.get("retake_needed", [])

    if overall_pass:
        new_status: Literal["all_clear", "waiting_for_retry"] = "all_clear"
    else:
        new_status = "waiting_for_retry"

    return {
        **state,
        "status": new_status,
        "summary": summary,
        "failures": retake_list,
        "room_results": {r.get("room_name", f"room_{r['photo_id']}"): True for r in summary.get("room_assignments", []) if r.get("review_status") == "passed"},
        "attempt_count": state["attempt_count"] + 1,
    }


def notify_owner(state: ReviewState) -> ReviewState:
    _post_agent_message(
        state["job_id"],
        "✅ All rooms look clean. Ready for your review!",
    )
    return state


def request_retry(state: ReviewState) -> ReviewState:
    for f in state["failures"]:
        _post_agent_message(
            state["job_id"],
            f"❌ {f.get('room_name', 'Room')}: {f.get('reason', 'Needs improvement')}. Please retake.",
        )
    return state


def wait_for_new_photo(state: ReviewState) -> ReviewState:
    if state["attempt_count"] >= state["max_attempts"]:
        _post_system_message(
            state["job_id"],
            "⚠️ Max retries reached. Manual review needed.",
        )
    return state


def route_after_review(state: ReviewState) -> Literal["notify_owner", "request_retry"]:
    return "notify_owner" if state["status"] == "all_clear" else "request_retry"


def route_from_wait(state: ReviewState) -> Literal[END, "fetch_context"]:
    if state["attempt_count"] >= state["max_attempts"]:
        return END
    return "fetch_context"


def build_review_graph():
    builder = StateGraph(ReviewState)

    builder.add_node("fetch_context", fetch_context)
    builder.add_node("review_photos", review_photos)
    builder.add_node("notify_owner", notify_owner)
    builder.add_node("request_retry", request_retry)
    builder.add_node("wait_for_new_photo", wait_for_new_photo)

    builder.add_edge(START, "fetch_context")
    builder.add_edge("fetch_context", "review_photos")
    builder.add_conditional_edges("review_photos", route_after_review)
    builder.add_edge("notify_owner", END)
    builder.add_edge("request_retry", "wait_for_new_photo")
    builder.add_conditional_edges("wait_for_new_photo", route_from_wait)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


review_graph = build_review_graph()
