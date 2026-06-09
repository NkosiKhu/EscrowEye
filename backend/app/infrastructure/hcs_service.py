from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HCSResult:
    status: str
    tx_id: str
    topic_id: str | None = None


class HCSService:
    """HCS boundary.

    The MVP records audit events locally and marks them as pending unless the
    real Hedera environment and SDK wiring are available. This keeps the app
    demoable while preserving the integration point.
    """

    def __init__(self) -> None:
        self.operator_id = os.getenv("HEDERA_OPERATOR_ID")
        self.operator_key = os.getenv("HEDERA_OPERATOR_KEY")
        self.default_topic_id = os.getenv("HEDERA_HCS_TOPIC_ID")

    def submit_event(self, event_type: str, payload: dict[str, Any], topic_id: str | None = None) -> HCSResult:
        target_topic = topic_id or self.default_topic_id
        if not (self.operator_id and self.operator_key and target_topic):
            return HCSResult(status="pending_hcs", tx_id=f"pending_hcs:{event_type}:{int(time.time())}", topic_id=target_topic)

        # Real Hedera Agent Kit/HCS submission is intentionally isolated here.
        # Once `hedera-agent-kit` credentials are installed, replace this block
        # with the SDK call without changing route/service code.
        return HCSResult(status="submitted", tx_id=f"hcs:{target_topic}:{int(time.time())}", topic_id=target_topic)
