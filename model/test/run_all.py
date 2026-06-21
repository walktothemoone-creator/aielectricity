"""통합 검증 러너 — API 연동 검증 + 예측(predict) 검증을 한 번에 실행한다.

API 검증( ai_elec/tests/test_api_verify.py )과
예측 검증( ai_elec/tests/test_predict_verify.py )의 개별 섹션을 순차 호출하고
하나의 종합 요약을 출력한다.

실행 방법:
    cd model
    python3 -m test.run_all
    python3 -m test.run_all --region 경기도 --horizon 5
    python3 -m test.run_all --real          # 실제 API 수집 후 예측까지 검증
    python3 -m test.run_all --skip-backtest  # 백테스트 섹션 생략(빠른 실행)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# model/ 를 import 경로에 추가 (ai_elec, predict_rnd 패키지 접근용)
_MODEL_ROOT = Path(__file__).resolve().parents[1]
if str(_MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEL_ROOT))

from ai_elec.config import settings
from ai_elec.tests import test_api_verify as api
from ai_elec.tests import test_predict_verify as pred

PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"
BAR = "═" * 70


def _banner(title: str) -> None:
    print("\n" + BAR)
    print(f"  {title}")
    print(BAR)


def run(region: str, days: int, horizon: int,
        real: bool, backtest: bool) -> int:
    print(BAR)
    print("  aielectricity — 통합 검증 (API 연동 + 예측 파이프라인)")
    print(f"  region={region}  days={days}  horizon={horizon}일  "
          f"real={real}  backtest={backtest}")
    print(BAR)

    results: list[tuple[str, bool]] = []
    use_mock = not settings.DATA_GO_KR_KEY

    # ── PART A. 공공데이터 API 연동 검증 ──────────────────────────────────
    _banner("PART A. 공공데이터 API 연동 검증")
    results.append(("API:설정", api.verify_settings()))
    results.append(("API:전력거래소", api.verify_power(region, use_mock)))
    results.append(("API:기상청", api.verify_weather(region, days, use_mock)))
    results.append(("API:통계청KOSIS", api.verify_industry(region, use_mock)))
    results.append(("API:통합", api.verify_integration(region, days)))

    # ── PART B. 예측(predict) 파이프라인 검증 ─────────────────────────────
    _banner("PART B. 예측(predict) 파이프라인 검증")
    results.append(("PRED:모듈", pred.verify_module()))
    results.append(("PRED:build_frame", pred.verify_build_frame(region)))
    results.append(("PRED:predict_mock", pred.verify_predict_mock(region, horizon)))
    if real:
        results.append(("PRED:predict_real", pred.verify_predict_real(region, horizon)))
    results.append(("PRED:predict_node", pred.verify_predict_node(region, horizon)))
    if backtest:
        results.append(("PRED:backtest", pred.verify_backtest(region)))

    # ── 종합 요약 ─────────────────────────────────────────────────────────
    _banner("종합 결과")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        mark = PASS if ok else FAIL
        print(f"  {mark}  {name}")
    print(f"\n  {passed}/{total} 섹션 통과")

    if use_mock:
        print(f"\n  (참고) DATA_GO_KR_KEY 미설정 → 일부 API 항목은 mock 데이터로 검증")

    if passed == total:
        print(f"\n  {PASS}  통합 검증 완료")
        print(BAR)
        return 0
    print(f"\n  {FAIL}  일부 섹션 실패 — 위 로그 확인")
    print(BAR)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="API 연동 + 예측 통합 검증")
    parser.add_argument("--region", default="대구광역시",
                        choices=list(settings.REGIONS.keys()))
    parser.add_argument("--days", type=int, default=3, help="API 날씨 예보 일수")
    parser.add_argument("--horizon", type=int, default=3, help="예측 일수")
    parser.add_argument("--real", action="store_true",
                        help="실제 API 수집 후 예측까지 검증")
    parser.add_argument("--skip-backtest", action="store_true",
                        help="predict_rnd 백테스트 섹션 생략")
    args = parser.parse_args(argv)

    return run(
        region=args.region,
        days=args.days,
        horizon=args.horizon,
        real=args.real,
        backtest=not args.skip_backtest,
    )


if __name__ == "__main__":
    sys.exit(main())
