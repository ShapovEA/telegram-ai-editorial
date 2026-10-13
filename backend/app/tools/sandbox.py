import base64
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


class SandboxError(Exception):
    pass


@dataclass
class SandboxResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    images: list[bytes] = field(default_factory=list)
    duration_ms: int = 0

    def summary(self, limit: int = 4000) -> str:
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout.strip()[:limit])
        if self.stderr.strip():
            parts.append("STDERR:\n" + self.stderr.strip()[-2000:])
        if self.images:
            parts.append(f"Сохранено графиков: {len(self.images)}")
        return "\n".join(parts) or "(пустой вывод)"


async def run_python(code: str, *, files: dict[str, str] | None = None, timeout: int = 20) -> SandboxResult:
    s = get_settings()
    payload: dict[str, Any] = {"code": code, "files": files or {}, "timeout": timeout}
    try:
        async with httpx.AsyncClient(timeout=timeout + 15) as client:
            resp = await client.post(f"{s.sandbox_url}/run", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        raise SandboxError(f"Песочница недоступна: {exc}") from exc
    return SandboxResult(
        ok=bool(data.get("ok")),
        stdout=data.get("stdout", ""),
        stderr=data.get("stderr", ""),
        images=[base64.b64decode(x) for x in data.get("images", [])],
        duration_ms=int(data.get("duration_ms", 0)),
    )
