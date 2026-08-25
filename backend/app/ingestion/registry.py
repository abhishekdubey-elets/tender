"""Adapter registry.

Adapters self-register via the ``@register_adapter`` decorator. The pipeline and
CLI look adapters up by name, so adding a source is purely additive — no other
module imports the concrete adapter classes directly.
"""
from __future__ import annotations

from app.ingestion.base import SourceAdapter

_REGISTRY: dict[str, type[SourceAdapter]] = {}


def register_adapter(cls: type[SourceAdapter]) -> type[SourceAdapter]:
    name = getattr(cls, "name", None)
    if not name:
        raise TypeError(f"{cls.__name__} must define 'name' before registration")
    if name in _REGISTRY and _REGISTRY[name] is not cls:
        raise ValueError(f"adapter name '{name}' already registered")
    _REGISTRY[name] = cls
    return cls


def get_adapter(name: str) -> type[SourceAdapter]:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"no adapter registered under '{name}'") from None


def list_adapters() -> dict[str, type[SourceAdapter]]:
    return dict(_REGISTRY)
