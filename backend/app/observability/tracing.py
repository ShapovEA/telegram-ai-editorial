import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from app.config import get_settings

log = logging.getLogger(__name__)

_client = None
_enabled = False


class _NoopObservation:
    def update(self, **_: Any) -> "_NoopObservation":
        return self

    def end(self, **_: Any) -> None:
        return None


def _get_client():
    global _client
    if _client is not None:
        return _client
    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key, base_url=s.langfuse_base_url)
    except Exception:
        log.warning("langfuse init failed", exc_info=True)
        _client = None
    return _client


def set_enabled(value: bool) -> None:
    global _enabled
    _enabled = value


def is_active() -> bool:
    return _enabled and _get_client() is not None


@contextmanager
def observe(name: str, as_type: str = "span", **kwargs: Any):
    if not is_active():
        yield _NoopObservation()
        return
    client = _get_client()
    try:
        cm = client.start_as_current_observation(name=name, as_type=as_type, **kwargs)
        obs = cm.__enter__()
    except Exception:
        log.debug("langfuse observation failed", exc_info=True)
        yield _NoopObservation()
        return
    try:
        yield obs
    except BaseException as exc:
        try:
            obs.update(level="ERROR", status_message=str(exc)[:500])
        except Exception:
            pass
        cm.__exit__(type(exc), exc, exc.__traceback__)
        raise
    else:
        cm.__exit__(None, None, None)


@asynccontextmanager
async def trace_run(name: str, *, run_id: str, channel_id: int | None, kind: str, input: Any = None):
    if not is_active():
        yield _NoopObservation()
        return
    from langfuse import propagate_attributes

    with propagate_attributes(
        session_id=f"channel-{channel_id}" if channel_id else None,
        user_id=str(channel_id) if channel_id else None,
        tags=[kind],
        metadata={"run_id": run_id},
        trace_name=name,
    ):
        with observe(name, as_type="agent", input=input, metadata={"run_id": run_id}) as obs:
            yield obs


def flush() -> None:
    client = _get_client()
    if client is not None:
        try:
            client.flush()
        except Exception:
            log.debug("langfuse flush failed", exc_info=True)
