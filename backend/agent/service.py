from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openrouter import ChatOpenRouter

from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from app.database import db, now_iso
from .graph import review_graph
from .prompts import ASSISTANT_SYSTEM_PROMPT
from .tools import (
    associate_photo,
    award_bid,
    confirm_job,
    create_home,
    create_job,
    dispute_job,
    fund_escrow,
    get_bids,
    get_homes,
    get_job,
    get_jobs,
    get_messages,
    get_photos,
    mark_ready,
    place_bid,
    send_message as tool_send_message,
    set_agent_jwt,
)

_AGENT_JWT = os.getenv("AGENT_JWT", "")


def _post_agent_message(job_id: int, body: str) -> dict:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO messages (job_id, sender_user_id, sender_type, body, created_at) VALUES (?, NULL, 'agent', ?, ?)",
            (job_id, body, now_iso()),
        )
        msg = conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(msg)


def _load_conversation(job_id: int) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
    return [dict(r) for r in rows]


async def trigger_assistant(job_id: int, user_id: int, body: str, user_type: str) -> None:
    """Called when user sends a message in agent mode. Runs the assistant LLM with tools."""
    set_agent_jwt(_AGENT_JWT)

    llm = ChatOpenRouter(
        model=OPENROUTER_MODEL,
        temperature=0,
        openrouter_api_key=OPENROUTER_API_KEY,
    )

    available_tools = [
        get_jobs, get_job, create_job,
        get_homes, create_home,
        place_bid, get_bids, award_bid,
        fund_escrow, mark_ready,
        tool_send_message, get_messages,
        get_photos, associate_photo,
        confirm_job, dispute_job,
    ]
    llm_with_tools = llm.bind_tools(available_tools)
    tool_map = {t.name: t for t in available_tools}

    system_prompt = ASSISTANT_SYSTEM_PROMPT.format(user_id=user_id, user_type=user_type)
    conversation = _load_conversation(job_id)

    messages: list = [SystemMessage(content=system_prompt)]
    for msg in conversation:
        if msg["sender_type"] == "human":
            messages.append(HumanMessage(content=msg["body"]))
        elif msg["sender_type"] == "agent":
            messages.append(HumanMessage(content=msg["body"]))
        else:
            messages.append(HumanMessage(content=f"[system] {msg['body']}"))

    response = await llm_with_tools.ainvoke(messages)

    if response.tool_calls:
        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn is None:
                continue
            try:
                result = await tool_fn.ainvoke(tc["args"])
            except Exception as exc:
                result = {"error": str(exc)}

            messages.append(HumanMessage(
                content=f"Tool {tc['name']} returned: {json.dumps(result, default=str)}"
            ))

        response = await llm_with_tools.ainvoke(messages)

    _post_agent_message(job_id, response.content)


async def trigger_review(job_id: int) -> None:
    """Called when photos are uploaded. Invokes the review graph."""
    initial_state = {
        "job_id": job_id,
        "status": "pending",
        "attempt_count": 0,
        "max_attempts": 3,
        "messages": [],
        "room_results": {},
        "job": None,
        "rooms": [],
        "photos": [],
        "summary": None,
        "failures": [],
    }
    config = {"configurable": {"thread_id": str(job_id)}}
    await review_graph.ainvoke(initial_state, config)
