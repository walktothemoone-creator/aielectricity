"""LangGraph 노드 간 공유 상태 ElecState.

agriculture 의 AgriState 대응. 모든 노드는 이 dict 만 읽고 쓴다.
"""
from __future__ import annotations

from typing import Any, TypedDict


class ElecState(TypedDict, total=False):
    # 입력
    region: str
    horizon_days: int

    # collect 노드 산출
    weather: dict[str, Any]
    power: dict[str, Any]
    indpop: dict[str, Any]
    sources: dict[str, str]      # collector명 -> source(api/mock)

    # predict 노드 산출
    forecast: dict[str, Any]     # Forecast 직렬화

    # strategy 노드 산출 (LLM)
    strategy: dict[str, Any]     # {summary, option_a, option_b, swot}

    # decision 노드 산출 (Bayesian)
    decision: dict[str, Any]

    # report 노드 산출
    report: str

    # 진단
    errors: list[str]
