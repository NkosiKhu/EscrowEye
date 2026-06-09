from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol


class HCSConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class HCSResult:
    status: str
    tx_id: str
    topic_id: str | None = None


class HCSClient(Protocol):
    def submit_message(self, topic_id: str, message: str) -> HCSResult:
        ...


class HieroHCSClient:
    def __init__(self, operator_id: str, operator_key: str) -> None:
        try:
            from hiero_sdk_python import Client, PrivateKey, TopicMessageSubmitTransaction
        except ImportError as exc:
            raise HCSConfigurationError("hiero_sdk_python_not_installed") from exc

        self._topic_submit_transaction = TopicMessageSubmitTransaction
        self._operator_key = PrivateKey.from_string(operator_key)
        self._client = Client()
        self._client.set_operator(operator_id, self._operator_key)

    def submit_message(self, topic_id: str, message: str) -> HCSResult:
        transaction = (
            self._topic_submit_transaction(topic_id=topic_id, message=message)
            .freeze_with(self._client)
            .sign(self._operator_key)
        )
        response = transaction.execute(self._client)
        tx_id = str(getattr(response, "transaction_id", response))
        return HCSResult(status="submitted", tx_id=tx_id, topic_id=topic_id)


class HCSService:
    """HCS boundary.

    The MVP records audit events locally and marks them as pending unless the
    real Hedera environment and SDK wiring are available. This keeps the app
    demoable while preserving the integration point.
    """

    def __init__(self, client_factory: Callable[[str, str], HCSClient] | None = None) -> None:
        self.operator_id = os.getenv("HEDERA_OPERATOR_ID")
        self.operator_key = os.getenv("HEDERA_OPERATOR_KEY")
        self.default_topic_id = os.getenv("HEDERA_HCS_TOPIC_ID")
        self._client_factory = client_factory or HieroHCSClient

    @property
    def require_real(self) -> bool:
        return os.getenv("HEDERA_HCS_REQUIRE_REAL", "").lower() in {"1", "true", "yes", "on"}

    def submit_event(self, event_type: str, payload: dict[str, Any], topic_id: str | None = None) -> HCSResult:
        target_topic = topic_id or self.default_topic_id
        if not (self.operator_id and self.operator_key and target_topic):
            if self.require_real:
                raise HCSConfigurationError("missing_hedera_hcs_credentials")
            return HCSResult(status="pending_hcs", tx_id=f"pending_hcs:{event_type}:{int(time.time())}", topic_id=target_topic)

        message = json.dumps({"event_type": event_type, "payload": payload, "created_at": int(time.time())}, separators=(",", ":"), sort_keys=True)
        try:
            return self._client_factory(self.operator_id, self.operator_key).submit_message(target_topic, message)
        except HCSConfigurationError:
            if self.require_real:
                raise
            return HCSResult(status="pending_hcs", tx_id=f"pending_hcs:{event_type}:{int(time.time())}", topic_id=target_topic)
