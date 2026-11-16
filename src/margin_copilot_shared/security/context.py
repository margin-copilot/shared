"""The validated caller of the current request, readable anywhere in its async context."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from margin_copilot_shared.security.tokens import Caller


@dataclass(frozen=True)
class RequestContext:
    caller: Caller
    token: str = field(repr=False)


_current: ContextVar[RequestContext] = ContextVar("margin_copilot_request")


def current_request() -> RequestContext:
    try:
        return _current.get()
    except LookupError:
        raise RuntimeError("no authenticated request in this context") from None


@contextmanager
def request_scope(context: RequestContext) -> Iterator[None]:
    reset = _current.set(context)
    try:
        yield
    finally:
        _current.reset(reset)
