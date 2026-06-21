"""공통 HTTP 클라이언트 + TTL 캐시 + fallback 베이스.

모든 collector 는 BaseCollector 를 상속한다.
- fetch(): 실제 API 호출. 실패하거나 USE_MOCK 면 mock() 로 우회.
- mock(): 결정론적(seed 고정) 더미 데이터. 데모 재현성 보장.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

import requests

from ..config import settings

_CACHE: dict[str, tuple[float, Any]] = {}


def _cache_key(*parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()


def cached_get(url: str, params: dict, ttl: int = settings.CACHE_TTL_SECONDS) -> dict:
    """GET + JSON, TTL 캐시. 네트워크/파싱 실패 시 예외를 그대로 올린다."""
    key = _cache_key(url, sorted(params.items()))
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]

    resp = requests.get(url, params=params, timeout=settings.HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    _CACHE[key] = (now, data)
    return data


class BaseCollector:
    name = "base"

    def collect(self, **kwargs) -> dict:
        """공개 진입점. 항상 dict 를 반환하며 절대 예외를 밖으로 던지지 않는다."""
        if settings.USE_MOCK:
            return self._wrap(self.mock(**kwargs), source="mock(forced)")
        try:
            return self._wrap(self.fetch(**kwargs), source="api")
        except Exception as exc:  # noqa: BLE001  — graceful degradation
            return self._wrap(self.mock(**kwargs), source=f"mock(fallback:{type(exc).__name__})")

    # 하위 클래스가 구현 ----------------------------------------------------
    def fetch(self, **kwargs) -> dict:
        raise NotImplementedError

    def mock(self, **kwargs) -> dict:
        raise NotImplementedError

    # 내부 -----------------------------------------------------------------
    def _wrap(self, payload: dict, source: str) -> dict:
        return {"collector": self.name, "source": source, "data": payload}
