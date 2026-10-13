from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from app.domain.schemas import DEFAULT_ROLE_MODELS, RoleModel


@dataclass
class RunContext:
    run_id: str | None = None
    channel_id: int | None = None
    channel_type: str | None = None
    post_id: int | None = None
    kind: str = ""
    role_models: dict[str, RoleModel] = field(default_factory=dict)
    budget_usd: float | None = None
    seq: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def model_for(self, role: str) -> RoleModel:
        if role in self.role_models:
            return self.role_models[role]
        return DEFAULT_ROLE_MODELS[role]


_run_ctx: ContextVar[RunContext | None] = ContextVar("run_ctx", default=None)
_node: ContextVar[str | None] = ContextVar("node", default=None)


def current_run() -> RunContext:
    ctx = _run_ctx.get()
    if ctx is None:
        ctx = RunContext()
        _run_ctx.set(ctx)
    return ctx


def set_run(ctx: RunContext):
    return _run_ctx.set(ctx)


def reset_run(token) -> None:
    _run_ctx.reset(token)


def current_node() -> str | None:
    return _node.get()


def set_node(name: str | None):
    return _node.set(name)


def reset_node(token) -> None:
    _node.reset(token)
