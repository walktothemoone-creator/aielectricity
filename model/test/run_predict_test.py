"""예측 검증 전용 러너 — 예측(predict) 파이프라인만 검증한다.

ai_elec/tests/test_predict_verify.py 의 개별 섹션을 호출하고 종합 요약을 출력한다.
(API 검증은 run_api_test.py, 둘 다 한 번에는 run_all.py 를 사용)

실행 방법:
    cd model
    python3 -m test.run_predict_test
    python3 -m test.run_predict_test --region 경기도 --horizon 5
    python3 -m test.run_predict_test --real          # 실제 API 수집 후 예측까지
    python3 -m test.run_predict_test --skip-backtest  # 백테스트 생략(빠른 실행)
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
from ai_elec.tests import test_predict_verify as pred

PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"
BAR = "═" * 70


def run(region: str, horizon: int, real: bool, backtest: bool) -> int:
    print(BAR)
    print("  aielectricity — 예측(predict) 파이프라인 검증")
    print(f"  region={region}  horizon={horizon}일  real={real}  backtest={backtest}")
    print(BAR)

    results: list[tuple[str, bool]] = [
        ("PRED:모듈", pred.verify_module()),
        ("PRED:build_frame", pred.verify_build_frame(region)),
        ("PRED:predict_mock", pred.verify_predict_mock(region, horizon)),
    ]
    if real:
        results.append(("PRED:predict_real", pred.verify_predict_real(region, horizon)))
    results.append(("PRED:predict_node", pred.verify_predict_node(region, horizon)))
    if backtest:
        results.append(("PRED:backtest", pred.verify_backtest(region)))

    print("\n" + BAR)
    print("  종합 결과")
    print(BAR)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print(f"  {PASS if ok else FAIL}  {name}")
    print(f"\n  {passed}/{total} 섹션 통과")

    if passed == total:
        print(f"\n  {PASS}  예측 파이프라인 검증 완료")
        print(BAR)
        return 0
    print(f"\n  {FAIL}  일부 섹션 실패 — 위 로그 확인")
    print(BAR)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="예측(predict) 파이프라인 검증")
    parser.add_argument("--region", default="대구광역시",
                        choices=list(settings.REGIONS.keys()))
    parser.add_argument("--horizon", type=int, default=3, help="예측 일수")
    parser.add_argument("--real", action="store_true",
                        help="실제 API 수집 후 예측까지 검증")
    parser.add_argument("--skip-backtest", action="store_true",
                        help="predict_rnd 백테스트 섹션 생략")
    args = parser.parse_args(argv)
    return run(
        region=args.region,
        horizon=args.horizon,
        real=args.real,
        backtest=not args.skip_backtest,
    )


if __name__ == "__main__":
    sys.exit(main())
