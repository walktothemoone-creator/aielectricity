"""공공데이터 API 연동 검증 스크립트.

각 API가 실제로 응답하는지, 응답 구조가 예상대로인지 확인한다.
API 키가 없으면 해당 항목은 SKIP으로 표시하고 계속 진행한다.

실행 방법:
    cd model
    python -m ai_elec.tests.test_api_verify
    python -m ai_elec.tests.test_api_verify --region 경기도 --days 2
"""
from __future__ import annotations

import argparse
import sys
import time

from ..config import settings
from ..collectors.power import PowerCollector
from ..collectors.weather import WeatherCollector
from ..collectors.industry import IndustryPopulationCollector

# ────────────────────────────────────────────────────────────────────────────
# 출력 헬퍼
# ────────────────────────────────────────────────────────────────────────────
PASS  = "\033[32m[PASS]\033[0m"
FAIL  = "\033[31m[FAIL]\033[0m"
SKIP  = "\033[33m[SKIP]\033[0m"
INFO  = "\033[36m[INFO]\033[0m"
WARN  = "\033[33m[WARN]\033[0m"
SEP   = "─" * 70


def _ok(label: str, detail: str = "") -> None:
    print(f"  {PASS} {label}" + (f"  →  {detail}" if detail else ""))


def _fail(label: str, reason: str) -> None:
    print(f"  {FAIL} {label}  →  {reason}")


def _skip(label: str, reason: str) -> None:
    print(f"  {SKIP} {label}  →  {reason}")


def _info(msg: str) -> None:
    print(f"  {INFO} {msg}")


# ────────────────────────────────────────────────────────────────────────────
# 검증 케이스
# ────────────────────────────────────────────────────────────────────────────

def verify_settings() -> bool:
    """설정값 및 API 키 존재 여부 점검."""
    print(f"\n{SEP}")
    print("1. 설정(config.py / settings) 및 API 키 점검")
    print(SEP)

    ok = True

    try:
        import config as cfg
        _ok("config.py 로드", f"MODEL_ROOT={cfg.MODEL_ROOT.name}")
        if settings.DATA_GO_KR_KEY == cfg.DATA_GO_KR_KEY:
            _ok("config ↔ settings 동기화", "DATA_GO_KR_KEY 일치")
        else:
            _fail("config ↔ settings", "DATA_GO_KR_KEY 불일치")
            ok = False
    except Exception as exc:  # noqa: BLE001
        _fail("config.py 로드", str(exc))
        ok = False

    # 필수 키
    checks = [
        ("DATA_GO_KR_KEY",  settings.DATA_GO_KR_KEY,  "전력거래소·기상청 필수"),
        ("KMA_KEY",         settings.KMA_KEY,          "기상청 (미설정 시 DATA_GO_KR_KEY 재사용)"),
        ("KOSIS_KEY",       settings.KOSIS_KEY,        "통계청 KOSIS"),
        ("GEMINI_API_KEY",  settings.GEMINI_API_KEY,   "Gemini LLM (없으면 규칙기반 fallback)"),
    ]
    for name, val, desc in checks:
        if val:
            _ok(f"{name} 설정됨", desc)
        else:
            _skip(f"{name} 미설정", f"{desc} — mock fallback 동작")

    _info(f"USE_MOCK={settings.USE_MOCK}  |  CACHE_TTL={settings.CACHE_TTL_SECONDS}s  |  HTTP_TIMEOUT={settings.HTTP_TIMEOUT}s")

    if not settings.DATA_GO_KR_KEY:
        _info("DATA_GO_KR_KEY 없음 → 전체 API 검증을 mock 모드로 진행합니다")
        ok = False

    # REGIONS 등록 여부
    if settings.REGIONS:
        _ok(f"REGIONS 등록", f"{len(settings.REGIONS)}개 행정구역")
    else:
        _fail("REGIONS 미등록", "settings.REGIONS 가 비어있음")
        ok = False

    return ok


def verify_power(region: str, use_mock: bool) -> bool:
    """전력거래소 API 또는 mock 검증."""
    print(f"\n{SEP}")
    label = "2. 전력거래소 — PowerCollector"
    print(f"{label}  (region={region}, mock={use_mock})")
    print(SEP)

    if not use_mock and not settings.DATA_GO_KR_KEY:
        _skip("API 호출 생략", "DATA_GO_KR_KEY 미설정")
        use_mock = True

    t0 = time.perf_counter()
    result = PowerCollector().collect(region=region, history_days=30)
    elapsed = time.perf_counter() - t0

    source = result.get("source", "")
    data   = result.get("data", {})
    ok = True

    # source 확인
    if "mock" in source and not use_mock:
        _fail("source", f"API 호출 실패, fallback 발동: {source}")
        ok = False
    else:
        _ok("source", source)

    # 필수 필드
    required = ["region", "nationwide_current_mw", "nationwide_peak_mw", "region_share", "history"]
    for f in required:
        if f in data:
            _ok(f"data.{f}", str(data[f])[:60])
        else:
            _fail(f"data.{f}", "필드 누락")
            ok = False

    # history 구조
    history = data.get("history", [])
    if len(history) >= 1:
        sample = history[0]
        if "date" in sample and "demand_mwh" in sample:
            _ok("history[0] 구조", f"date={sample['date']}  demand_mwh={sample['demand_mwh']:,.1f} MWh")
        else:
            _fail("history[0] 구조", f"예상 키 없음: {list(sample.keys())}")
            ok = False
        _info(f"history 레코드 수: {len(history)}일")
    else:
        _fail("history", "레코드 없음")
        ok = False

    # region_share 범위
    share = data.get("region_share", 0)
    if 0 < share <= 1:
        _ok("region_share 범위", f"{share} (0 < x ≤ 1 ✓)")
    else:
        _fail("region_share 범위", f"{share} — 기대값: 0~1")
        ok = False

    _info(f"소요 시간: {elapsed:.3f}s")
    return ok


def verify_weather(region: str, days: int, use_mock: bool) -> bool:
    """기상청 단기예보 API 또는 mock 검증."""
    print(f"\n{SEP}")
    print(f"3. 기상청 단기예보 — WeatherCollector  (region={region}, days={days}, mock={use_mock})")
    print(SEP)

    if not use_mock and not settings.KMA_KEY:
        _skip("API 호출 생략", "KMA_KEY 미설정")
        use_mock = True

    t0 = time.perf_counter()
    result = WeatherCollector().collect(region=region, days=days)
    elapsed = time.perf_counter() - t0

    source  = result.get("source", "")
    data    = result.get("data", {})
    records = data.get("records", [])
    ok = True

    if "mock" in source and not use_mock:
        _fail("source", f"API 호출 실패, fallback 발동: {source}")
        ok = False
    else:
        _ok("source", source)

    # records 개수
    if len(records) >= 1:
        _ok(f"records 수", f"{len(records)}일 (요청: {days}일)")
    else:
        _fail("records", "레코드 없음")
        ok = False

    # 각 레코드 필드 검증
    required_keys = {"date", "temp_avg", "temp_max", "temp_min", "precip_prob", "humidity"}
    for i, rec in enumerate(records):
        missing = required_keys - set(rec.keys())
        if missing:
            _fail(f"records[{i}] 누락 필드", str(missing))
            ok = False
        else:
            _ok(f"records[{i}]",
                f"date={rec['date']}  temp_avg={rec['temp_avg']}℃  "
                f"precip={rec['precip_prob']}%  humidity={rec['humidity']}%")

        # 기온 합리성 (한국 기준 -40 ~ 45℃)
        t = rec.get("temp_avg", 0)
        if not (-40 <= t <= 45):
            _fail(f"records[{i}].temp_avg 범위", f"{t}℃ — 비정상")
            ok = False

    _info(f"소요 시간: {elapsed:.3f}s")
    return ok


def verify_industry(region: str, use_mock: bool) -> bool:
    """통계청 KOSIS API 또는 mock 검증."""
    print(f"\n{SEP}")
    print(f"4. 통계청 KOSIS — IndustryPopulationCollector  (region={region}, mock={use_mock})")
    print(SEP)

    if not use_mock and not settings.KOSIS_KEY:
        _skip("API 호출 생략", "KOSIS_KEY 미설정")
        use_mock = True

    t0 = time.perf_counter()
    result = IndustryPopulationCollector().collect(region=region)
    elapsed = time.perf_counter() - t0

    source = result.get("source", "")
    data   = result.get("data", {})
    ok = True

    if "mock" in source and not use_mock:
        _fail("source", f"API 호출 실패, fallback 발동: {source}")
        ok = False
    else:
        _ok("source", source)

    required = ["region", "grdp_trillion", "industry_sales_index", "population_k", "population_yoy_pct"]
    for f in required:
        if f in data:
            _ok(f"data.{f}", str(data[f]))
        else:
            _fail(f"data.{f}", "필드 누락")
            ok = False

    # 값 합리성
    pop = data.get("population_k", 0)
    if pop > 0:
        _ok("population_k > 0", f"{pop:,.1f} 천명")
    else:
        _fail("population_k", f"{pop} — 0 이하")
        ok = False

    grdp = data.get("grdp_trillion", 0)
    if grdp > 0:
        _ok("grdp_trillion > 0", f"{grdp} 조원")
    else:
        _fail("grdp_trillion", f"{grdp} — 0 이하")
        ok = False

    _info(f"소요 시간: {elapsed:.3f}s")
    return ok


def verify_integration(region: str, days: int) -> bool:
    """세 collector 동시 호출 후 predict_node 입력 포맷 충족 여부 검증."""
    print(f"\n{SEP}")
    print(f"5. 통합 검증 — collect_node 시뮬레이션  (region={region})")
    print(SEP)

    ok = True
    power  = PowerCollector().collect(region=region, history_days=60)
    weather = WeatherCollector().collect(region=region, days=days)
    indpop = IndustryPopulationCollector().collect(region=region)

    # predict_node 가 요구하는 경로 점검
    checks = [
        (power,   "power.data.history",          lambda d: isinstance(d["data"]["history"], list) and len(d["data"]["history"]) > 0),
        (weather, "weather.data.records",         lambda d: isinstance(d["data"]["records"], list) and len(d["data"]["records"]) > 0),
        (indpop,  "indpop.data.grdp_trillion",   lambda d: isinstance(d["data"]["grdp_trillion"], (int, float))),
        (indpop,  "indpop.data.industry_sales_index", lambda d: isinstance(d["data"]["industry_sales_index"], (int, float))),
        (indpop,  "indpop.data.population_k",    lambda d: isinstance(d["data"]["population_k"], (int, float))),
    ]
    for obj, path, check_fn in checks:
        try:
            passed = check_fn(obj)
            if passed:
                _ok(path)
            else:
                _fail(path, "타입 또는 값 오류")
                ok = False
        except (KeyError, TypeError) as e:
            _fail(path, str(e))
            ok = False

    # history 날짜 형식 YYYYMMDD 검증
    history = power["data"].get("history", [])
    if history:
        sample_date = history[0].get("date", "")
        if len(sample_date) == 8 and sample_date.isdigit():
            _ok("history date 형식", f"YYYYMMDD ✓  샘플={sample_date}")
        else:
            _fail("history date 형식", f"'{sample_date}' — YYYYMMDD 아님")
            ok = False

    # records 날짜 형식 YYYYMMDD 검증
    records = weather["data"].get("records", [])
    if records:
        sample_date = records[0].get("date", "")
        if len(sample_date) == 8 and sample_date.isdigit():
            _ok("weather records date 형식", f"YYYYMMDD ✓  샘플={sample_date}")
        else:
            _fail("weather records date 형식", f"'{sample_date}' — YYYYMMDD 아님")
            ok = False

    _info("모든 collector 출력이 predict_node 입력 포맷을 충족하는지 확인 완료")
    return ok


# ────────────────────────────────────────────────────────────────────────────
# 진입점
# ────────────────────────────────────────────────────────────────────────────

def run(region: str = "서울특별시", days: int = 3) -> None:
    print("=" * 70)
    print("  aielectricity — 공공데이터 API 연동 검증")
    print("=" * 70)
    print(f"  대상 지역: {region}  |  예측 일수: {days}일")

    has_key = bool(settings.DATA_GO_KR_KEY)
    use_mock = not has_key

    results = {
        "설정 점검":       verify_settings(),
        "전력거래소 API":  verify_power(region, use_mock),
        "기상청 API":      verify_weather(region, days, use_mock),
        "통계청 KOSIS":    verify_industry(region, use_mock),
        "통합(collect) 검증": verify_integration(region, days),
    }

    print(f"\n{'=' * 70}")
    print("  최종 결과 요약")
    print("=" * 70)
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    for name, ok in results.items():
        mark = PASS if ok else FAIL
        print(f"  {mark} {name}")
    print(f"\n  {passed}/{total} 항목 통과")

    if not has_key:
        print(f"\n  {WARN} API 키 미설정 — mock 데이터로 검증했습니다.")
        print(f"       .env 에 DATA_GO_KR_KEY 를 입력하면 실제 API 연동 검증이 가능합니다.")

    print("=" * 70)

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="공공데이터 API 연동 검증")
    parser.add_argument("--region", default="서울특별시", choices=list(settings.REGIONS.keys()))
    parser.add_argument("--days",   type=int, default=3)
    args = parser.parse_args()
    run(region=args.region, days=args.days)
