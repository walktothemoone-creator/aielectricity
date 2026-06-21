"""LangGraph 그래프 조립.

collect → predict → decision → strategy → report

langgraph 가 없으면 동일 순서의 순차 실행기로 graceful fallback 한다.
"""
from __future__ import annotations

from .nodes import (
    collect_node,
    decision_node,
    predict_node,
    report_node,
    strategy_node,
)
from .state import ElecState

_ORDER = [
    ("collect", collect_node),
    ("predict", predict_node),
    ("decision", decision_node),
    ("strategy", strategy_node),
    ("report", report_node),
]


def build_graph():
    """compiled graph (invoke(state)->state) 를 반환."""
    try:
        from langgraph.graph import END, START, StateGraph

        g = StateGraph(ElecState)
        for name, fn in _ORDER:
            g.add_node(name, fn)
        g.add_edge(START, _ORDER[0][0])
        for (n1, _), (n2, _) in zip(_ORDER, _ORDER[1:]):
            g.add_edge(n1, n2)
        g.add_edge(_ORDER[-1][0], END)
        return g.compile()
    except Exception:  # noqa: BLE001 — langgraph 미설치 등
        return _SequentialGraph()


class _SequentialGraph:
    """langgraph 미설치 시 동일 의미의 순차 실행기."""

    def invoke(self, state: dict) -> dict:
        st = dict(state)
        for _, fn in _ORDER:
            st.update(fn(st))
        return st
