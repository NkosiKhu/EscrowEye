# EscrowEye — Agent Architecture

> How the AI agent fits into the app: one agent, two modes, same REST API as the UI.

---

## Table of Contents

1. [Philosophy](#1-philosophy)
2. [Architecture Overview](#2-architecture-overview)
3. [Mode 1: Assistant (User-Driven)](#3-mode-1-assistant-user-driven)
4. [Mode 2: Photo Reviewer (Auto-Triggered)](#4-mode-2-photo-reviewer-auto-triggered)
5. [LangGraph State Graph](#5-langgraph-state-graph)
6. [Tool Definitions](#6-tool-definitions)
7. [LLM Prompt Strategy](#7-llm-prompt-strategy)
8. [How the Frontend Sees It](#8-how-the-frontend-sees-it)

---

## 1. Philosophy

- **One agent** — not a fleet of specialized sub-agents. The same agent handles form-filling, bidding, chatting, and photo review.
- **Same API** — every tool the agent calls maps to a REST endpoint the frontend also uses. There is no separate "agent API."
- **Human-in-the-loop by default** — the agent proposes actions. The user confirms through the UI or chat. The only autonomous path is photo review (and even that just posts messages — it doesn't release funds).
- **Conversation as the interface** — the agent lives in the same chat as human messages. No separate agent dashboard.

---

## 2. Architecture Overview

```
┌───────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                           │
│                                                                │
│  POST /api/jobs/:id/messages                                   │
│       │                                                        │
│       ▼                                                        │
│  ┌─────────────────────────────────┐                           │
│  │  Message Handler                │                           │
│  │  └─ has photo_ids? ──→ trigger  │                           │
│  │       no              LangGraph │                           │
│  │       │              Reviewer   │                           │
│  │       ▼                        │                           │
│  │  Normal chat flow              │                           │
│  └─────────────────────────────────┘                           │
│                                                                │
│  The agent itself runs as a background process:                │
│  ┌────────────────────────────────────────────────┐            │
│  │  EscrowEye Agent (LangGraph)                   │            │
│  │                                                │            │
│  │  Runtime: Python, asyncio, LangGraph           │            │
│  │  LLM: gpt-4o-mini (via LangChain ChatOpenAI)   │            │
│  │  Tools: all call FastAPI internally (httpx)    │            │
│  │  State: per-job, persisted to SQLite           │            │
│  └────────────────────────────────────────────────┘            │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

### Where the agent runs

In-process background task on the FastAPI server. When a message with photos arrives, the handler fires `asyncio.create_task(agent.review_photos(job_id))`. The agent runs in the same Python process, calls the same database, and posts messages back through the same message service.

For the hackathon this is fine. If it becomes a bottleneck, spin it into a separate worker process later.

---

## 3. Mode 1: Assistant (User-Driven)

### Trigger

User sends a message in the conversational UI that doesn't have `photo_ids`. The backend routes it to the agent instead of storing it directly.

### What happens

```
User: "Bid 45 HBAR on job 3"

1. Agent receives: { job_id: 3, body: "Bid 45 HBAR on job 3", sender_id: current_user }
2. Agent interprets intent via LLM
3. Agent calls tool: place_bid(job_id=3, amount=45000000)
4. API returns: { bid_id: 5, status: "pending" }
5. Agent stores response as a system message in the conversation
6. Frontend refreshes: user sees "Bid of 45 HBAR placed on job 3 (bid #5)"
```

### What the user sees

```
┌─────────────────────────────────────────────┐
│  You: Bid 45 HBAR on job 3                   │
│  Agent: Bid of 45 HBAR placed on job 3        │
│         (bid #5, status: pending)             │
│                                              │
│  [Bid]  [View Job 3]  [Message]              │
└─────────────────────────────────────────────┘
```

### Supported intents

| Intent | Tool | Example |
|---|---|---|
| Create home | `create_home` | "Add my condo at 5th Avenue" |
| Post job | `create_job` | "Post a cleaning job for my beach house" |
| List jobs | `get_jobs` | "Show me open cleaning jobs" |
| Place bid | `place_bid` | "Bid 40 HBAR on job 3" |
| View bids | `get_bids` | "Who bid on job 3?" |
| Award bid | `award_bid` | "Accept bid #5 on job 3" |
| Fund escrow | `fund_escrow` | "Pay the escrow for job 3" |
| Send message | `send_message` | "Tell the supplier the kitchen looks great" |
| View photos | `get_photos` | "Show me the photos for job 3" |
| Confirm job | `confirm_job` | "Confirm job 3 is complete" |
| Dispute job | `dispute_job` | "Dispute job 3, the bathroom wasn't cleaned" |

---

## 4. Mode 2: Photo Reviewer (Auto-Triggered)

### Trigger

`POST /api/jobs/:id/messages` with `photo_ids` non-empty. The handler stores the message, then fires the review agent in the background.

### Flow

```
1. Supplier uploads 3 photos via the UI
   → POST /api/jobs/3/messages { body: "Before photos", photo_ids: [1,2,3] }
   
2. Backend saves the message, then starts the reviewer:
   asyncio.create_task(review_agent.run(job_id=3))
   
3. Review agent:
   a. Loads job details (instructions, rooms)
   b. Loads photo metadata (CIDs, sequence numbers)
   c. Decrypts each photo using the EscrowEye server key
   d. Sends to LLM with a structured prompt
   e. Decides: pass or retry per room

4a. ALL PASS:
    → Agent calls associate_photo for each room assignment
    → Agent posts message: "✅ All rooms look clean. Job approved."
    → Job status → awaiting_confirmation (owner can now confirm)

4b. FAILURES:
    → Agent posts message: "❌ Kitchen needs more work. The counters are still dirty."
    → Job stays in_progress
    → Supplier sees the feedback in the chat, uploads more photos
    → Agent re-runs on next photo upload
```

### Review prompt (abridged)

```
You are reviewing photos for a cleaning job.

Job instructions: {instructions}
Rooms to clean: {room_names}

Photo {sequence}: appears to show {room_guess}. 
Does this room pass the cleaning check? 
Be specific about what's wrong if it fails.

Respond in JSON:
{
  "room_assignments": [{ "photo_id": 1, "room": "Kitchen" }],
  "results": [
    { "photo_id": 1, "room": "Kitchen", "pass": true },
    { "photo_id": 2, "room": "Bathroom", "pass": false, "reason": "Sink is visibly dirty" }
  ]
}
```

### Room-to-photo association

The agent is the only component that associates photos with rooms. The `photos.room_id` field is set by the agent during review. This happens server-side so the agent can see the actual image (decrypted with the EscrowEye key).

---

## 5. LangGraph State Graph

### State

```python
class ReviewState(TypedDict):
    job_id: int
    status: Literal["pending", "reviewing", "waiting_for_retry", "approved"]
    attempt_count: int
    max_attempts: int  # default 3
    messages: list[dict]  # conversation so far
    room_results: dict[str, bool]  # { "Kitchen": True, "Bathroom": False }
```

### Graph

```
                    ┌──────────┐
                    │  START   │
                    └────┬─────┘
                         │
                         ▼
                 ┌─────────────────┐
                 │  fetch_context   │── Load job, rooms, photos, messages
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │  review_photos   │── LLM call: analyze photos
                 └────────┬────────┘
                          │
                    ┌─────┴─────┐
                    │           │
                    ▼           ▼
            ┌──────────┐  ┌──────────┐
            │  passed   │  │  failed  │
            └────┬─────┘  └────┬─────┘
                 │             │
                 ▼             ▼
        ┌────────────────┐  ┌─────────────────────┐
        │  approve_job   │  │  request_retry       │
        │  (set awaiting │  │  (post system msg)    │
        │   confirmation)│  └──────────┬────────────┘
        └───────┬────────┘             │
                │                      ▼
                │              ┌──────────────┐
                │              │  wait_for_new │─── sleep / webhook
                │              │  _photos      │
                │              └──────┬───────┘
                │                     │
                │            ┌────────┴────────┐
                │            │                 │
                │         timeout           new photo
                │         (max 3)           arrives
                │            │                 │
                │            ▼                 │
                │     ┌──────────┐             │
                │     │  escalate│             │
                │     │  to owner│             │
                │     └──────────┘             │
                │                              │
                │                              ▼
                │                     ┌───────────────┐
                │                     │  review_photos │── loop back
                │                     │  (retry count  │
                │                     │   +1)          │
                │                     └───────────────┘
                │
                ▼
          ┌──────────┐
          │   END    │
          └──────────┘
```

### Node implementations

```python
def fetch_context(state: ReviewState) -> ReviewState:
    job = get_job(state["job_id"])
    rooms = get_rooms_for_job(job["home_id"])
    photos = get_photos(state["job_id"])
    messages = get_messages(state["job_id"])
    return {**state, "job": job, "rooms": rooms, "photos": photos, "messages": messages}


def review_photos(state: ReviewState) -> ReviewState:
    prompt = build_review_prompt(state["job"], state["rooms"], state["photos"])
    result = llm.invoke(prompt)

    # Parse JSON result
    for r in result["room_assignments"]:
        associate_photo(r["photo_id"], r["room"])

    failures = [r for r in result["results"] if not r["pass"]]
    if not failures:
        return {**state, "status": "approved"}
    else:
        return {**state, "status": "waiting_for_retry",
                "failures": failures, "attempt_count": state["attempt_count"] + 1}


def approve_job(state: ReviewState) -> ReviewState:
    send_message(state["job_id"], "✅ All rooms look clean. Job is ready for your confirmation.", sender="system")
    update_job_status(state["job_id"], "awaiting_confirmation")
    return state


def request_retry(state: ReviewState) -> ReviewState:
    for f in state["failures"]:
        send_message(state["job_id"], f"❌ {f['room']}: {f['reason']}. Please retake.", sender="system")
    return state


def wait_for_new_photo(state: ReviewState) -> ReviewState:
    if state["attempt_count"] >= state["max_attempts"]:
        send_message(state["job_id"], "⚠️ Max retries reached. Manual review needed.", sender="system")
        return {**state, "end": True}  # escape to END
    # Agent sleeps — next photo upload will trigger a new review cycle
    return state


def route_after_review(state: ReviewState) -> Literal["approve_job", "request_retry"]:
    return "approve_job" if state["status"] == "approved" else "request_retry"
```

### Graph builder

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(ReviewState)

builder.add_node("fetch_context", fetch_context)
builder.add_node("review_photos", review_photos)
builder.add_node("approve_job", approve_job)
builder.add_node("request_retry", request_retry)
builder.add_node("wait_for_new_photo", wait_for_new_photo)

builder.add_edge(START, "fetch_context")
builder.add_edge("fetch_context", "review_photos")
builder.add_conditional_edges("review_photos", route_after_review)
builder.add_edge("approve_job", END)
builder.add_edge("request_retry", "wait_for_new_photo")
```

### Persistence

LangGraph checkpointer stores state per `job_id`:

```python
from langgraph.checkpoint.memory import MemorySaver
# For hackathon: in-memory. For prod: SQLiteSaver or PostgresSaver.

checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)

# Resume a review cycle on next photo upload
state = graph.get_state({"job_id": 3})
```

---

## 6. Tool Definitions

Every tool wraps a FastAPI endpoint call via `httpx.AsyncClient`. The agent runs in-process, so it calls the API internally (same DB, same service layer).

| Tool | Input | Output | Calls |
|---|---|---|---|
| `get_jobs(status=None)` | filter string | JSON job list | `GET /api/jobs` |
| `get_job(job_id)` | int | JSON job object | `GET /api/jobs/:id` |
| `create_job(title, home_id, ...)` | fields | JSON job object | `POST /api/jobs` |
| `get_homes()` | none | JSON home list | `GET /api/homes` |
| `create_home(name, address)` | fields | JSON home | `POST /api/homes` |
| `place_bid(job_id, amount, msg)` | fields | JSON bid | `POST /api/jobs/:id/bids` |
| `get_bids(job_id)` | int | JSON bid list | `GET /api/jobs/:id/bids` |
| `award_bid(job_id, bid_id)` | ints | JSON job | `POST /api/jobs/:id/award` |
| `fund_escrow(job_id, signed_tx)` | int, string | JSON job | `POST /api/jobs/:id/fund` |
| `send_message(job_id, body, photo_ids)` | fields | JSON message | `POST /api/jobs/:id/messages` |
| `get_messages(job_id)` | int | JSON message list | `GET /api/jobs/:id/messages` |
| `get_photos(job_id)` | int | JSON photo list | `GET /api/jobs/:id/photos` |
| `associate_photo(photo_id, room_id)` | ints | JSON photo | `PATCH /api/photos/:id` |
| `confirm_job(job_id, signature)` | int, string | JSON job | `POST /api/jobs/:id/confirm` |
| `dispute_job(job_id, reason)` | fields | JSON job | `POST /api/jobs/:id/dispute` |

### Tool registration with LangChain

```python
from langchain_core.tools import tool

@tool
async def place_bid(job_id: int, amount: int, message: str = "") -> dict:
    """Place a bid on a job. Amount is in tinybars."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE}/jobs/{job_id}/bids",
            json={"amount": amount, "message": message},
            headers={"Authorization": f"Bearer {JWT}"}
        )
        return resp.json()
```

---

## 7. LLM Prompt Strategy

### Assistant prompt

```
You are the EscrowEye assistant. You help users manage property cleaning jobs.

You have access to tools that mirror the app's API. Use them to fulfill requests.

Rules:
- Confirm before executing destructive actions (dispute, confirm)
- For bids, clarify the amount if not specified
- If a user asks something you can't do with your tools, say so
- Keep responses short and actionable

Current user: {user_id}
User type: {user_type} ("owner" or "supplier")
```

### Reviewer prompt

```
You are the EscrowEye photo reviewer for cleaning job #{job_id}.

JOB INSTRUCTIONS:
{instructions}

ROOMS TO CLEAN:
{room_names}

The supplier has submitted photos. Review each one:

PHOTOS:
{photo_descriptions}

For each photo:
1. Identify which room it shows
2. Does the room pass cleaning standards? Consider: visible dirt, clutter, streaks, dust
3. If it fails, explain exactly what needs improvement

Respond with valid JSON only:
{
  "room_assignments": [{ "photo_id": 1, "room": "Kitchen" }],
  "results": [
    { "photo_id": 1, "room": "Kitchen", "pass": true },
    { "photo_id": 2, "room": "Bathroom", "pass": false, "reason": "Sink has visible stains" }
  ]
}
```

---

## 8. How the Frontend Sees It

The frontend doesn't need to know an agent exists. Same chat component renders everything.

```
┌───────────────────────────────────────────────┐
│  Job #3 — Clean My Beach House                 │
│  Status: In Progress                           │
├───────────────────────────────────────────────┤
│                                               │
│  [Supplier] Before photos of kitchen            │
│  📷 kitchen_1.jpg  📷 kitchen_2.jpg            │
│  [10:32 AM]                                    │
│                                               │
│  [System] ❌ Kitchen: Counters still have      │
│  crumbs. Please re-wipe and retake.             │
│  [10:33 AM]                                    │
│                                               │
│  [Supplier] Retook the kitchen photos           │
│  📷 kitchen_retake.jpg                         │
│  [10:45 AM]                                    │
│                                               │
│  [System] ✅ Kitchen passes. All rooms look    │
│  clean. Ready for your confirmation!            │
│  Job is awaiting your sign-off.                 │
│  [10:46 AM]                                    │
│                                               │
│  ┌─────────────────────────────────────────┐   │
│  │ Type a message...       [Send] [📷]    │   │
│  └─────────────────────────────────────────┘   │
│                                               │
│  [Confirm Job]  [Dispute]                     │
└───────────────────────────────────────────────┘
```

### Key points for the frontend dev

- Agent messages have `sender: "system"` or `sender: null` — render them with a muted style and a small robot icon.
- When `job.status` changes to `awaiting_confirmation`, show a **Confirm Job** button that triggers `POST /api/jobs/:id/confirm` with a HashPack signature.
- Photo upload opens the camera/file picker, then `POST /api/jobs/:id/photos` (multipart), then `POST /api/jobs/:id/messages` with the returned `photo_ids`.
- The chat input can also accept plain-text commands that get routed to the assistant agent. No special parsing needed — the agent handles intent recognition.

---

## Files / Modules

```
backend/
├── agent/
│   ├── __init__.py
│   ├── graph.py              # LangGraph builder + nodes
│   ├── tools.py              # LangChain tool definitions
│   ├── prompts.py            # Assistant + reviewer prompt templates
│   └── service.py            # Trigger + resume logic
└── routers/
    └── messages.py           # POST handler fires agent if photo_ids present
```
