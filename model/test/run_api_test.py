"""API 검증 전용 러너 — 공공데이터 API 연동만 검증한다.

ai_elec/tests/test_api_verify.py 의 개별 섹션을 호출하고 종합 요약을 출력한다.
(예측 검증은 run_predict_test.py, 둘 다 한 번에는 run_all.py 를 사용)

실행 방법:
    cd model
    python3 -m test.run_api_test
    python3 -m test.run_api_test --region 경기도 --days 5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# model/ 를 import 경로에 추가 (ai_elec 패키지 접근용)
_MODEL_ROOT = Path(__file__).resolve().parents[1]
if str(_MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEL_ROOT))

from ai_elec.config import settings
from ai_elec.tests import test_api_verify as api

PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"
BAR = "═" * 70


def run(region: str, days: int) -> int:
    print(BAR)
    print("  aielectricity — 공공데이터 API 연동 검증")
    print(f"  region={region}  days={days}")
    print(BAR)

    use_mock = not settings.DATA_GO_KR_KEY
    results: list[tuple[str, bool]] = [
        ("API:설정", api.verify_settings()),
        ("API:전력거래소", api.verify_power(region, use_mock)),
        ("API:기상청", api.verify_weather(region, days, use_mock)),
        ("API:통계청KOSIS", api.verify_industry(region, use_mock)),
        ("API:통합", api.verify_integration(region, days)),
    ]

    print("\n" + BAR)
    print("  종합 결과")
    print(BAR)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print(f"  {PASS if ok else FAIL}  {name}")
    print(f"\n  {passed}/{total} 섹션 통과")

    if use_mock:
        print(f"\n  (참고) DATA_GO_KR_KEY 미설정 → API 항목은 mock 데이터로 검증")

    if passed == total:
        print(f"\n  {PASS}  API 연동 검증 완료")
        print(BAR)
        return 0
    print(f"\n  {FAIL}  일부 섹션 실패 — 위 로그 확인")
    print(BAR)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="공공데이터 API 연동 검증")
    parser.add_argument("--region", default="대구광역시",
                        choices=list(settings.REGIONS.keys()))
    parser.add_argument("--days", type=int, default=3, help="날씨 예보 일수")
    args = parser.parse_args(argv)
    return run(region=args.region, days=args.days)


if __name__ == "__main__":
    sys.exit(main())
