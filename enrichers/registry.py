# enrichers/registry.py
"""enricher_name → class 映射。"""

from __future__ import annotations

_REGISTRY: dict[str, type] = {}
_ORDER: list[str] = []


def register(name: str):
    """装饰器：注册 enricher。注册顺序即执行顺序（快的优先）。"""
    def decorator(cls):
        cls.name = name
        _REGISTRY[name] = cls
        if name not in _ORDER:
            _ORDER.append(name)
        return cls
    return decorator


def list_enrichers() -> list[type]:
    if not _REGISTRY:
        _load_all()
    return [_REGISTRY[name] for name in _ORDER]


def get_enricher(name: str) -> type | None:
    if not _REGISTRY:
        _load_all()
    return _REGISTRY.get(name)


def _load_all():
    # 顺序即优先级：纯规则 → 纯 DB → HN API → GitHub API → LLM 抽取
    import enrichers.content_quality  # noqa: F401
    import enrichers.cross_reference  # noqa: F401
    import enrichers.hn_comments  # noqa: F401
    import enrichers.github_ecosystem  # noqa: F401
    import enrichers.entity_extraction  # noqa: F401
