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
- **Agent recommends, owner decides** — the agent never changes job status. It posts review results as messages; the owner confirms via the UI.
- **Three message types** — `human` (normal user), `agent` (bot responses in chat), `system` (status banners). All three render in the same conversation.
- **Conversation as the interface** — the agent lives in the same chat as human messages. No separate agent dashboard.

---

## 2. Architecture Overview

```
┌───────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                           │
│                                                                │
│  POST /api/jobs/{job_id}/messages                              │
│       │                                                        │
│       ▼                                                        │
│  ┌─────────────────────────────────┐                           │
│  │  Message Handler                │                           │
│  │  └─ Always stores human msg     │                           │
│  │       │                         │                           │
│  │       ├─ has photo_ids? ──────→ LangGraph Reviewer          │
│  │       ├─ agent mode? ─────────→ Assistant Agent             │
│  │       └─ otherwise ───────────→ Normal chat only            │
│  └─────────────────────────────────┘                           │
│                                                                │
│  The agent itself runs as a background process:                │
│  ┌────────────────────────────────────────────────┐            │
│  │  EscrowEye Agent (LangGraph)                   │            │
│  │                                                │            │
│  │  Runtime: Python, asyncio, LangGraph           │            │
│  │  LLM: openai/gpt-4o via ChatOpenRouter         │            │
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

User sends a message from the app's chat panel with agent mode enabled and no `photo_ids`. The backend stores the human message first, then invokes the assistant agent.

### What happens

```
User: "Bid 45 HBAR on job 3"

1. Backend stores the human message.
2. Agent receives: { job_id: 3, body: "Bid 45 HBAR on job 3", sender_user_id: current_user }
3. Agent interprets intent via LLM
4. Agent calls tool: place_bid(job_id=3, amount_tinybar=4500000000)
5. API returns: { id: 5, amount_tinybar: 4500000000, status: "pending" }
6. Agent stores its response as an `agent` message in the conversation
7. Frontend refreshes: user sees "Bid of 45 HBAR placed on job 3 (bid #5)"
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
| Mark ready | `mark_ready` | "Mark job 3 ready for review" |
| Confirm job | `confirm_job` | "Confirm job 3 is complete" |
| Dispute job | `dispute_job` | "Dispute job 3, the bathroom wasn't cleaned" |

### Paid job creation path

When the user asks the chat-panel agent to create a job, the agent gathers the missing job fields and calls `create_job`. If the API returns `402 Payment Required`, the frontend opens the x402/Blocky402 payment flow. After the user approves payment with HashPack, the frontend replays the same `POST /api/jobs` request. The agent then posts a normal `agent` message confirming the job was created and linking to the new job workspace.

---

## 4. Mode 2: Photo Reviewer (Auto-Triggered)

### Trigger

`POST /api/jobs/{job_id}/messages` with `photo_ids` non-empty. The handler stores the human message, then fires the review agent in the background.

### Flow

```
1. Supplier uploads 3 photos via the UI
   → POST /api/jobs/3/messages { body: "Before photos", photo_ids: [1,2,3] }
   
2. Backend saves the message, then starts the reviewer:
   asyncio.create_task(review_agent.run(job_id=3))
   
3. Review agent:
   a. Loads job details (room names, access_notes)
   b. Loads photo metadata (CIDs, sequence numbers)
   c. Decrypts each photo using the EscrowEye server key
   d. **Stage 1 — per-photo analysis**: resizes each image with Pillow, base64-encodes it, and sends it to `openai/gpt-4o` through `ChatOpenRouter` for room identification + cleanliness rating
   e. **Stage 2 — summary decision**: feeds all per-photo results into the LLM for a final pass/fail per room

4a. ALL PASS:
    → Agent calls associate_photo for each room assignment/review result
    → Agent posts message: "✅ All rooms look clean. Ready for your review!"
    → Owner sees the "all clear" in chat and decides whether to confirm via the UI

4b. FAILURES:
    → Agent posts message: "❌ Kitchen needs more work. The counters are still dirty."
    → Job stays in_progress
    → Supplier sees the feedback in the chat, uploads more photos
    → Agent re-runs on next photo upload
```

### Review prompts

#### Stage 1 — per-photo (multimodal, image + text)

```
You are evaluating a cleaning photo for job #{job_id}.

Rooms to clean: {rooms_with_ids}

Photo data: {base64_image}

Respond in JSON only:
{
  "room_id": 1,
  "room_name": "Kitchen",
  "confidence": 0.95,
  "cleanliness_score": 3,
  "pass": false,
  "issues": ["Counters have visible crumbs", "Floor needs mopping"]
}

- room_id: the matching room id from the provided room list
- room_name: the matching room name
- confidence: 0-1 how sure you are about the room
- cleanliness_score: 1-5 (5 = spotless)
- pass: true if score >= 4
- issues: list of specific problems if score < 4
```

#### Stage 2 — summary (text only)

```
You are summarizing the photo review for cleaning job #{job_id}.

Rooms to clean: {rooms_with_ids}

Per-photo results:
{stage_1_results}

Decide:
- Which photos pass/fail overall
- Associate each photo to a room
- Overall verdict: all clean or specific retakes needed

Respond in JSON only:
{
  "room_assignments": [
    { "photo_id": 1, "room_id": 1, "review_status": "failed" }
  ],
  "overall_pass": false,
  "retake_needed": [
    { "room_id": 1, "room_name": "Kitchen", "reason": "Counters still dirty" }
  ],
  "summary": "Kitchen needs a retake. Bathroom and living room look good."
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
    status: Literal["pending", "reviewing", "waiting_for_retry", "all_clear"]
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
        │  notify_owner   │  │  request_retry       │
        │  (post all-clear│  │  (post system msg)    │
        │   message)      │  └──────────┬────────────┘
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
    per_photo_results = analyze_photos_multimodal(state["job"], state["rooms"], state["photos"])
    summary = summarize_results(per_photo_results)

    for r in summary["room_assignments"]:
        associate_photo(
            job_id=state["job_id"],
            photo_id=r["photo_id"],
            room_id=r["room_id"],
            review_status=r["review_status"],
        )

    if summary["overall_pass"]:
        return {**state, "status": "all_clear", "summary": summary}
    else:
        return {**state, "status": "waiting_for_retry",
                "failures": summary["retake_needed"],
                "attempt_count": state["attempt_count"] + 1}


def notify_owner(state: ReviewState) -> ReviewState:
    send_message(state["job_id"], "✅ All rooms look clean. Ready for your review!", sender_type="agent")
    # Agent does NOT change job status — owner confirms via UI
    return state


def request_retry(state: ReviewState) -> ReviewState:
    for f in state["failures"]:
        send_message(state["job_id"], f"❌ {f['room_name']}: {f['reason']}. Please retake.", sender_type="agent")
    return state


def wait_for_new_photo(state: ReviewState) -> ReviewState:
    if state["attempt_count"] >= state["max_attempts"]:
        send_message(state["job_id"], "⚠️ Max retries reached. Manual review needed.", sender_type="system")
        return {**state, "end": True}  # escape to END
    # Agent sleeps — next photo upload will trigger a new review cycle
    return state


def route_after_review(state: ReviewState) -> Literal["notify_owner", "request_retry"]:
    return "notify_owner" if state["status"] == "all_clear" else "request_retry"
```

### Graph builder

```python
from langgraph.graph import StateGraph, START, END

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
| `get_job(job_id)` | int | JSON job object | `GET /api/jobs/{job_id}` |
| `create_job(title, home_id, ...)` | fields | JSON job object | `POST /api/jobs` |
| `get_homes()` | none | JSON home list | `GET /api/homes` |
| `create_home(name, address)` | fields | JSON home | `POST /api/homes` |
| `place_bid(job_id, amount_tinybar, msg)` | fields | JSON bid | `POST /api/jobs/{job_id}/bids` |
| `get_bids(job_id)` | int | JSON bid list | `GET /api/jobs/{job_id}/bids` |
| `award_bid(job_id, bid_id)` | ints | JSON job | `POST /api/jobs/{job_id}/award` |
| `fund_escrow(job_id, signed_tx)` | int, string | JSON job | `POST /api/jobs/{job_id}/fund` |
| `mark_ready(job_id, message)` | fields | JSON job | `POST /api/jobs/{job_id}/mark-ready` |
| `send_message(job_id, body, photo_ids)` | fields | JSON message | `POST /api/jobs/{job_id}/messages` |
| `get_messages(job_id)` | int | JSON message list | `GET /api/jobs/{job_id}/messages` |
| `get_photos(job_id)` | int | JSON photo list | `GET /api/jobs/{job_id}/photos` |
| `associate_photo(job_id, photo_id, room_id, review_status)` | fields | JSON photo | `PATCH /api/jobs/{job_id}/photos/{photo_id}` |
| `confirm_job(job_id, signature)` | int, string | JSON job | `POST /api/jobs/{job_id}/confirm` |
| `dispute_job(job_id, reason)` | fields | JSON job | `POST /api/jobs/{job_id}/dispute` |

### Tool registration with LangChain

```python
from langchain_core.tools import tool

@tool
async def place_bid(job_id: int, amount_tinybar: int, message: str = "") -> dict:
    """Place a bid on a job. Amount is in tinybars."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE}/jobs/{job_id}/bids",
            json={"amount_tinybar": amount_tinybar, "message": message},
            headers={"Authorization": f"Bearer {JWT}"}
        )
        return resp.json()
```

---

## 7. LLM Prompt Strategy

### Model provider

Use OpenRouter for both assistant and reviewer calls:

```python
from langchain_openrouter import ChatOpenRouter

llm = ChatOpenRouter(
    model="openai/gpt-4o",
    temperature=0,
)
```

Do not use `ChatOpenAI` with an OpenRouter `base_url` override. `langchain-openrouter` provides the first-party `ChatOpenRouter` integration for LangGraph, structured output, tracing, tool calling, multimodal inputs, and provider routing.

For reviewer image calls, pass images as OpenRouter-compatible multimodal content blocks:

```python
from langchain_core.messages import HumanMessage

message = HumanMessage(
    content=[
        {"type": "text", "text": prompt_text},
        {
            "type": "image",
            "base64": base64_image,
            "mime_type": "image/jpeg",
        },
    ],
)

response = llm.invoke([message])
```

This is the LangChain `ChatOpenRouter` shape. If calling OpenRouter's raw chat completions API directly, use the OpenAI-compatible `image_url` content part with a `data:image/jpeg;base64,...` URL.

### Assistant prompt

```
You are the EscrowEye assistant. You help users manage property cleaning jobs.

You have access to tools that mirror the app's API. Use them to fulfill requests.

Rules:
- Confirm before executing destructive actions (dispute, confirm)
- For wallet-required actions, prepare the action and let the UI collect the HashPack/x402 signature or payment
- If `create_job` returns `402 Payment Required`, tell the UI to present the x402 payment flow and replay the request after payment
- For bids, clarify the amount if not specified
- If a user asks something you can't do with your tools, say so
- Keep responses short and actionable

Current user: {user_id}
User type: {user_type} ("owner" or "supplier")
```

### Reviewer prompt (Stage 1 — per-photo multimodal)

```
You are evaluating a cleaning photo for job #{job_id}.

Rooms to clean: {rooms_with_ids}

Photo data: {base64_image}

Respond in JSON only:
{
  "room_id": 1,
  "room_name": "Kitchen",
  "confidence": 0.95,
  "cleanliness_score": 3,
  "pass": false,
  "issues": ["Counters have visible crumbs", "Floor needs mopping"]
}

- room_id: the matching room id from the provided room list
- room_name: the matching room name
- confidence: 0-1 how sure you are about the room
- cleanliness_score: 1-5 (5 = spotless)
- pass: true if score >= 4
- issues: list of specific problems if score < 4
```

### Reviewer prompt (Stage 2 — text-only summary)

```
You are summarizing the photo review for cleaning job #{job_id}.

Rooms to clean: {rooms_with_ids}

Per-photo results:
{stage_1_results}

Decide:
- Which photos pass/fail overall
- Associate each photo to a room
- Overall verdict: all clean or specific retakes needed

Respond in JSON only:
{
  "room_assignments": [
    { "photo_id": 1, "room_id": 1, "review_status": "failed" }
  ],
  "overall_pass": false,
  "retake_needed": [
    { "room_id": 1, "room_name": "Kitchen", "reason": "Counters still dirty" }
  ],
  "summary": "Kitchen needs a retake. Bathroom and living room look good."
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

- The UI is a normal hosted shadcn-style app. The agent appears as a full-height or full-screen chat panel that can replace manual setup when the user prefers it.
- `sender_type` values: `"human"` (normal bubble + avatar), `"agent"` (robot icon, lighter bg), `"system"` (muted banner, centered).
- When the agent posts an all-clear message, show a **Confirm Job** button that triggers `POST /api/jobs/{job_id}/confirm` with a HashPack signature.
- Photo upload opens the camera/file picker, then `POST /api/jobs/{job_id}/photos` (multipart), then `POST /api/jobs/{job_id}/messages` with the returned `photo_ids`.
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
    └── messages.py           # POST handler stores message, then fires reviewer/assistant when needed
```
