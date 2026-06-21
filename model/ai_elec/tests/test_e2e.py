"""3 시나리오 E2E 검증 (mock 모드에서 항상 통과해야 함).

S1: 수도권 대도시(서울) — 큰 수요, 예측·전략 정상 산출
S2: 산업도시(울산) — 높은 GRDP slow-feature 반영
S3: 소규모(제주) — 데이터 적어도 fallback 으로 파이프라인 완주

실행: python -m ai_elec.tests.test_e2e
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_elec.services.agent_service import ElecAgentService  # noqa: E402

SCENARIOS = [
    ("서울특별시", 3),
    ("울산광역시", 5),
    ("제주특별자치도", 2),
]


def _check(result: dict, region: str, horizon: int) -> None:
    assert result["region"] == region
    fc = result["forecast"]
    assert fc["method"] in {"autogluon", "fallback_linear", "failed"}
    assert len(fc["predictions"]) == horizon, f"{region}: 예측 개수 불일치"
    for p in fc["predictions"]:
        assert p["demand_mwh"] > 0
        assert p["lower"] <= p["demand_mwh"] <= p["upper"]
    dec = result["decision"]
    assert 0.0 <= (dec["posterior_peak"] or 0) <= 1.0
    assert dec["recommended"] in {"hold", "demand_resp", "ramp_supply"}
    strat = result["strategy"]
    assert "option_a" in strat and "option_b" in strat
    assert isinstance(result["report"], str) and len(result["report"]) > 50


def main() -> int:
    svc = ElecAgentService()
    passed = 0
    for region, horizon in SCENARIOS:
        try:
            res = svc.run(region, horizon)
            _check(res, region, horizon)
            print(f"[PASS] {region} (h={horizon}) "
                  f"method={res['forecast']['method']} "
                  f"P(peak)={res['decision']['posterior_peak']} "
                  f"action={res['decision']['recommended']} "
                  f"src={res['sources']}")
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {region}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] {region}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(SCENARIOS)} scenarios passed")
    return 0 if passed == len(SCENARIOS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
