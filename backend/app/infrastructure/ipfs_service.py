from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings


class IPFSConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class IPFSUploadResult:
    cid: str
    storage_url: str
    gateway_url: str
    provider: str


class IPFSService:
    def __init__(self, http_client: Any | None = None) -> None:
        self._http_client = http_client

    @property
    def require_real(self) -> bool:
        return settings.IPFS_REQUIRE_REAL

    @property
    def pinata_jwt(self) -> str | None:
        return settings.PINATA_JWT

    @property
    def api_url(self) -> str:
        return settings.PINATA_API_URL

    @property
    def gateway_url(self) -> str:
        return settings.PINATA_GATEWAY_URL.rstrip("/")

    def upload_file(self, content: bytes, filename: str, content_type: str | None, metadata: dict[str, Any] | None = None) -> IPFSUploadResult:
        if not self.pinata_jwt:
            if self.require_real:
                raise IPFSConfigurationError("missing_pinata_jwt")
            cid = self._local_cid(content, filename)
            return self._result(cid, "local")

        payload_metadata = {"name": filename, "keyvalues": metadata or {}}
        data = {
            "pinataMetadata": json.dumps(payload_metadata, separators=(",", ":")),
            "pinataOptions": json.dumps({"cidVersion": 1}, separators=(",", ":")),
        }
        files = {"file": (filename, content, content_type or "application/octet-stream")}
        response = self._post(self.api_url, headers={"Authorization": f"Bearer {self.pinata_jwt}"}, files=files, data=data, timeout=60)
        cid = response.get("IpfsHash") or response.get("cid")
        if not cid:
            raise IPFSConfigurationError("pinata_response_missing_cid")
        return self._result(str(cid), "pinata")

    def _post(self, url: str, headers: dict[str, str], files: dict[str, tuple[str, bytes, str]], data: dict[str, str], timeout: int) -> dict[str, Any]:
        client = self._http_client or httpx.Client()
        response = client.post(url, headers=headers, files=files, data=data, timeout=timeout)
        if isinstance(response, dict):
            return response
        response.raise_for_status()
        return response.json()

    def _result(self, cid: str, provider: str) -> IPFSUploadResult:
        return IPFSUploadResult(
            cid=cid,
            storage_url=f"ipfs://{cid}",
            gateway_url=f"{self.gateway_url}/ipfs/{cid}",
            provider=provider,
        )

    def _local_cid(self, content: bytes, filename: str) -> str:
        digest = hashlib.sha256(filename.encode() + b":" + content).hexdigest()
        return "bafy" + digest[:45]
