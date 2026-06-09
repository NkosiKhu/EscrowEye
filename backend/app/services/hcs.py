from __future__ import annotations

import json
import os
import time

import requests
from loguru import logger
from hiero_sdk_python import (
    TopicCreateTransaction,
    TopicMessageSubmitTransaction,
    TopicId,
)

from .hedera_client import get_client, get_operator_key


class HcsService:
    def __init__(self) -> None:
        self.client = get_client()
        self.operator_key = get_operator_key()

    def create_topic(self, memo: str = "") -> str:
        tx = TopicCreateTransaction(memo=memo, admin_key=self.operator_key.public_key())
        tx.freeze_with(self.client)
        tx.sign(self.operator_key)
        receipt = tx.execute(self.client)
        return str(receipt.topic_id)

    def submit_message(self, topic_id: str, message: dict) -> dict:
        topic = TopicId.from_string(topic_id)
        tx = TopicMessageSubmitTransaction()
        tx.set_topic_id(topic)
        tx.set_message(json.dumps(message))
        tx.freeze_with(self.client)
        tx.sign(self.operator_key)
        receipt = tx.execute(self.client)
        try:
            running_hash = str(receipt.topic_running_hash or "")
        except Exception:
            running_hash = ""
        return {
            "sequence_number": receipt.topic_sequence_number,
            "consensus_timestamp": running_hash,
        }

    def query_messages(self, topic_id: str, limit: int = 50) -> list[dict]:
        network = os.getenv("HEDERA_NETWORK", "testnet")
        base = "https://testnet.mirrornode.hedera.com" if network == "testnet" else "https://mainnet.mirrornode.hedera.com"
        url = f"{base}/api/v1/topics/{topic_id}/messages?limit={limit}&order=asc"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for msg in data.get("messages", []):
            import base64
            try:
                decoded = base64.b64decode(msg["message"]).decode()
                content = json.loads(decoded)
            except Exception:
                content = {"raw": msg.get("message", "")}
            results.append({
                "sequence_number": msg["sequence_number"],
                "consensus_timestamp": msg["consensus_timestamp"],
                "message": content,
            })
        return results


def create_topic_for_job(job_id: int) -> str | None:
    try:
        svc = HcsService()
        topic_id = svc.create_topic(memo=f"escroweye-job-{job_id}")
        return topic_id
    except Exception as exc:
        logger.error("[hcs] Failed to create topic for job {}: {}", job_id, exc)
        return None


def submit_audit_event(topic_id: str, event_type: str, job_id: int, **extra) -> dict | None:
    try:
        svc = HcsService()
        message = {"type": event_type, "job_id": job_id}
        if event_type == "job_created":
            message["owner"] = extra.get("owner", "")
            message["suggested_price_tinybar"] = extra.get("suggested_price_tinybar", 0)
        elif event_type == "job_completed":
            message["tx_hash"] = extra.get("tx_hash", "")
        message["timestamp"] = time.time()
        result = svc.submit_message(topic_id, message)
        return result
    except Exception as exc:
        logger.error("[hcs] Failed to submit {} for job {}: {}", event_type, job_id, exc)
        return None
