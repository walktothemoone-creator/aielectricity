"""ElecAgentService — 그래프를 한 번 컴파일해 재사용하는 서비스 레이어."""
from __future__ import annotations

from ..agent.graph import build_graph


class ElecAgentService:
    def __init__(self):
        self._graph = build_graph()

    def run(self, region: str, horizon_days: int = 3) -> dict:
        state = {"region": region, "horizon_days": horizon_days, "errors": []}
        return self._graph.invoke(state)


# 간단 CLI
if __name__ == "__main__":
    import json
    import sys

    region = sys.argv[1] if len(sys.argv) > 1 else "서울특별시"
    result = ElecAgentService().run(region, 3)
    print(result["report"])
    print("\n--- raw forecast ---")
    print(json.dumps(result["forecast"], ensure_ascii=False, indent=2))
