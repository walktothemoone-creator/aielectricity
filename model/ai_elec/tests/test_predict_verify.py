"""전력수요 예측(predict) 검증 스크립트.

predictor 모듈·predict_node·predict_rnd 백테스트를 순차 검증한다.
API 키가 없어도 mock 데이터로 기본 검증은 진행된다.

실행 방법:
    cd model
    python3 -m ai_elec.tests.test_predict_verify
    python3 -m ai_elec.tests.test_predict_verify --region 경기도 --horizon 5
    python3 -m ai_elec.tests.test_predict_verify --backtest
    python3 -m ai_elec.tests.test_predict_verify --real   # 실제 API 수집 후 예측
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from ..agent.nodes import predict_node
from ..collectors.industry import IndustryPopulationCollector
from ..collectors.power import PowerCollector
from ..collectors.weather import WeatherCollector
from ..config import settings
from ..ml import predictor
from ..ml.predictor import Forecast, _build_frame

# predict_rnd (백테스트 섹션용)
_RND_ROOT = Path(__file__).resolve().parents[2]
if str(_RND_ROOT) not in sys.path:
    sys.path.insert(0, str(_RND_ROOT))

# ────────────────────────────────────────────────────────────────────────────
# 출력 헬퍼
# ────────────────────────────────────────────────────────────────────────────
PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"
SKIP = "\033[33m[SKIP]\033[0m"
INFO = "\033[36m[INFO]\033[0m"
WARN = "\033[33m[WARN]\033[0m"
SEP = "─" * 70


def _ok(label: str, detail: str = "") -> None:
    print(f"  {PASS} {label}" + (f"  →  {detail}" if detail else ""))


def _fail(label: str, reason: str) -> None:
    print(f"  {FAIL} {label}  →  {reason}")


def _skip(label: str, reason: str) -> None:
    print(f"  {SKIP} {label}  →  {reason}")


def _info(msg: str) -> None:
    print(f"  {INFO} {msg}")


def _header(title: str) -> None:
    print(f"\n{SEP}")
    print(title)
    print(SEP)


# ────────────────────────────────────────────────────────────────────────────
# mock 수집 페이로드
# ────────────────────────────────────────────────────────────────────────────

def _mock_collectors(region: str, horizon: int, history_days: int = 60) -> tuple[dict, dict, dict]:
    """collector mock() → predict() 입력 형식으로 래핑."""
    power = PowerCollector().mock(region=region, history_days=history_days)
    weather = WeatherCollector().mock(region=region, days=horizon)
    indpop = IndustryPopulationCollector().mock(region=region)
    return (
        {"source": "mock", "data": power},
        {"source": "mock", "data": weather},
        {"source": "mock", "data": indpop},
    )


def _real_collectors(region: str, horizon: int, history_days: int = 60) -> tuple[dict, dict, dict]:
    power = PowerCollector().collect(region=region, history_days=history_days)
    weather = WeatherCollector().collect(region=region, days=horizon)
    indpop = IndustryPopulationCollector().collect(region=region)
    return power, weather, indpop


def _validate_forecast(fc: Forecast, region: str, horizon: int) -> list[str]:
    """Forecast 객체 구조·값 검증. 오류 메시지 목록 반환."""
    errors: list[str] = []
    if fc.region != region:
        errors.append(f"region 불일치: {fc.region!r} != {region!r}")
    if fc.horizon_days != horizon:
        errors.append(f"horizon 불일치: {fc.horizon_days} != {horizon}")
    if len(fc.predictions) != horizon:
        errors.append(f"predictions 길이 {len(fc.predictions)} != horizon {horizon}")
    if fc.method not in ("autogluon", "fallback_linear"):
        errors.append(f"알 수 없는 method: {fc.method!r}")

    required_keys = {"date", "demand_mwh", "lower", "upper"}
    for i, p in enumerate(fc.predictions):
        missing = required_keys - p.keys()
        if missing:
            errors.append(f"predictions[{i}] 키 누락: {missing}")
            continue
        if p["demand_mwh"] <= 0:
            errors.append(f"predictions[{i}] demand_mwh <= 0: {p['demand_mwh']}")
        if p["lower"] > p["upper"]:
            errors.append(f"predictions[{i}] lower > upper")
        if not (p["lower"] <= p["demand_mwh"] <= p["upper"] + 1e-6):
            # 구간이 point를 완전히 포함하지 않을 수 있어 소폭 허용
            if abs(p["demand_mwh"] - p["lower"]) > abs(p["upper"] - p["lower"]) * 2:
                errors.append(f"predictions[{i}] demand가 구간 밖: {p}")
    return errors


# ────────────────────────────────────────────────────────────────────────────
# 검증 섹션
# ────────────────────────────────────────────────────────────────────────────

def verify_module() -> bool:
    _header("1. predictor 모듈·Forecast 구조 점검")
    ok = True
    try:
        fc = Forecast(region="테스트", horizon_days=3)
        _ok("Forecast dataclass 생성")
        if fc.method != "fallback_linear":
            _fail("Forecast 기본 method", f"expected fallback_linear, got {fc.method}")
            ok = False
        else:
            _ok("Forecast 기본 method", "fallback_linear")
    except Exception as exc:  # noqa: BLE001
        _fail("Forecast dataclass", str(exc))
        ok = False

    try:
        import autogluon.tabular  # noqa: F401
        _ok("AutoGluon 설치됨", "autogluon 경로 사용 가능")
    except ImportError:
        _skip("AutoGluon 미설치", "fallback_linear 로 예측")

    _info(f"지원 지역 {len(settings.REGIONS)}개")
    return ok


def verify_build_frame(region: str) -> bool:
    _header("2. _build_frame 피처 테이블 생성")
    ok = True
    power, weather, indpop = _mock_collectors(region, horizon=3, history_days=60)
    try:
        rows = _build_frame(power, weather, indpop)
        _ok(f"학습 row 생성", f"{len(rows)}건")
        if len(rows) < 20:
            _warn = f"AutoGluon 최소 20건 필요 — 현재 {len(rows)}건 (fallback 가능)"
            _info(_warn)

        sample = rows[0]
        feat_keys = {"date", "dow", "doy", "temp_avg", "cooling_load", "heating_load",
                     "grdp", "ind_sales", "pop", "demand_mwh"}
        missing = feat_keys - sample.keys()
        if missing:
            _fail("피처 컬럼", f"누락: {missing}")
            ok = False
        else:
            _ok("피처 컬럼", ", ".join(sorted(feat_keys)))
            _info(
                f"샘플 {sample['date']}: demand={sample['demand_mwh']:.1f} MWh, "
                f"temp={sample['temp_avg']:.1f}°C, pop={sample['pop']:.0f}k"
            )
    except Exception as exc:  # noqa: BLE001
        _fail("_build_frame", str(exc))
        ok = False
    return ok


def verify_predict_mock(region: str, horizon: int) -> bool:
    _header(f"3. predict() mock 데이터 검증  |  {region}  horizon={horizon}일")
    ok = True
    power, weather, indpop = _mock_collectors(region, horizon=horizon, history_days=60)

    t0 = time.perf_counter()
    try:
        fc = predictor.predict(power, weather, indpop, horizon=horizon)
        elapsed = time.perf_counter() - t0
        errs = _validate_forecast(fc, region, horizon)
        if errs:
            for e in errs:
                _fail("Forecast 검증", e)
            ok = False
        else:
            _ok("predict() 성공", f"method={fc.method}, {elapsed:.1f}s")
            for p in fc.predictions:
                _info(
                    f"  {p['date']}: {p['demand_mwh']:,.1f} MWh "
                    f"[{p['lower']:,.1f} ~ {p['upper']:,.1f}]"
                )
            if fc.feature_importance:
                top = sorted(fc.feature_importance.items(), key=lambda x: -abs(x[1]))[:3]
                _info("feature_importance 상위: " + ", ".join(f"{k}={v:.3f}" for k, v in top))
    except Exception as exc:  # noqa: BLE001
        _fail("predict()", str(exc))
        ok = False
    return ok


def verify_predict_real(region: str, horizon: int) -> bool:
    _header(f"4. predict() 실제 API 데이터 검증  |  {region}  horizon={horizon}일")
    if not settings.DATA_GO_KR_KEY:
        _skip("실제 API 예측", "DATA_GO_KR_KEY 미설정")
        return True

    ok = True
    t0 = time.perf_counter()
    try:
        power, weather, indpop = _real_collectors(region, horizon=horizon, history_days=60)
        sources = f"power={power['source']}, weather={weather['source']}, indpop={indpop['source']}"
        _info(f"수집 완료 ({time.perf_counter() - t0:.1f}s)  |  {sources}")

        hist_len = len(power["data"]["history"])
        if hist_len < 20:
            _info(f"history {hist_len}일 — AutoGluon 미달 시 fallback_linear 예상")

        fc = predictor.predict(power, weather, indpop, horizon=horizon)
        elapsed = time.perf_counter() - t0
        errs = _validate_forecast(fc, region, horizon)
        if errs:
            for e in errs:
                _fail("Forecast 검증", e)
            ok = False
        else:
            _ok("실제 데이터 predict() 성공", f"method={fc.method}, 총 {elapsed:.1f}s")
            for p in fc.predictions:
                _info(f"  {p['date']}: {p['demand_mwh']:,.1f} MWh")
    except Exception as exc:  # noqa: BLE001
        _fail("실제 API predict()", str(exc))
        ok = False
    return ok


def verify_predict_node(region: str, horizon: int) -> bool:
    _header(f"5. predict_node (LangGraph) 통합  |  {region}")
    ok = True
    power, weather, indpop = _mock_collectors(region, horizon=horizon, history_days=60)
    state = {
        "region": region,
        "horizon_days": horizon,
        "power": power,
        "weather": weather,
        "indpop": indpop,
        "errors": [],
    }
    try:
        out = predict_node(state)
        fc_dict = out.get("forecast", {})
        if fc_dict.get("method") == "failed":
            _fail("predict_node", f"errors={out.get('errors')}")
            return False
        if len(fc_dict.get("predictions", [])) != horizon:
            _fail("predict_node predictions", f"길이 {len(fc_dict.get('predictions', []))}")
            ok = False
        else:
            _ok("predict_node 반환", f"method={fc_dict.get('method')}")
            if out.get("errors"):
                _info(f"errors: {out['errors']}")
    except Exception as exc:  # noqa: BLE001
        _fail("predict_node", str(exc))
        ok = False
    return ok


def verify_backtest(region: str) -> bool:
    _header(f"6. predict_rnd 백테스트 (합성 데이터)  |  {region}")
    try:
        from predict_rnd.backtest import run_backtest, summarize
        from predict_rnd.data_generator import generate_daily, month_total
        from predict_rnd.models import available_models
    except ImportError as exc:
        _skip("predict_rnd import", str(exc))
        return True

    cfg = settings.REGIONS.get(region)
    if not cfg:
        _fail("지역 설정", f"{region} 없음")
        return False

    ok = True
    REF_TODAY = dt.date(2026, 6, 21)
    train_start = dt.date(2025, 1, 1)
    test_end = dt.date(2026, 5, 31)
    TARGET_MONTHS = [(2026, m) for m in range(1, 6)]

    _info(f"합성 데이터 생성 ({train_start} ~ {test_end})")
    all_daily = generate_daily(cfg, train_start, test_end, ref_today=REF_TODAY)
    _ok("generate_daily", f"{len(all_daily)}일")

    models = available_models()
    _info(f"모델: {', '.join(m.name for m in models)}")

    results = run_backtest(
        all_daily=all_daily,
        target_months=TARGET_MONTHS,
        models=models,
        min_train_days=90,
    )
    if not results:
        _fail("run_backtest", "결과 없음")
        return False

    summary = summarize(results)
    _ok("run_backtest 완료", f"{len(results)}건 (모델 {len(summary)}개)")

    print(f"\n  {'모델':>18}  {'평균정확도%':>10}  {'평균MAPE%':>10}  {'90%달성':>7}")
    print("  " + "─" * 52)
    for model_name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_accuracy_pct"]):
        mark = PASS if s["target_met"] else FAIL
        print(
            f"  {model_name:>18}  "
            f"{s['avg_accuracy_pct']:>10.2f}  "
            f"{s['avg_mape_pct']:>10.2f}  "
            f"  {mark}"
        )
        if s["avg_accuracy_pct"] < 50:
            _fail(f"{model_name} 정확도", f"{s['avg_accuracy_pct']:.1f}% — 비정상적으로 낮음")
            ok = False

    best = max(summary, key=lambda k: summary[k]["avg_accuracy_pct"])
    _info(f"최고 모델: {best} ({summary[best]['avg_accuracy_pct']:.2f}%)")

    # 월별 실제값 샘플 출력
    _info("2026년 1~5월 실제 합계 (MWh):")
    for year, month in TARGET_MONTHS[:2]:
        total = month_total(all_daily, year, month)
        _info(f"  {year}년{month:02d}월: {total:,.0f}")

    return ok


# ────────────────────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="전력수요 예측(predict) 검증")
    parser.add_argument("--region", default="대구광역시", choices=list(settings.REGIONS.keys()))
    parser.add_argument("--horizon", type=int, default=3, help="예측 일수 (기본 3)")
    parser.add_argument("--real", action="store_true", help="실제 API 수집 후 predict 검증")
    parser.add_argument("--backtest", action="store_true", help="predict_rnd 백테스트 섹션 실행")
    parser.add_argument("--all-regions", action="store_true", help="전 지역 mock predict 검증")
    args = parser.parse_args()

    print("=" * 70)
    print("  전력수요 예측(predict) 검증")
    print(f"  region={args.region}  horizon={args.horizon}일")
    print("=" * 70)

    results: list[tuple[str, bool]] = []

    results.append(("module", verify_module()))
    results.append(("build_frame", verify_build_frame(args.region)))
    results.append(("predict_mock", verify_predict_mock(args.region, args.horizon)))

    if args.real:
        results.append(("predict_real", verify_predict_real(args.region, args.horizon)))

    results.append(("predict_node", verify_predict_node(args.region, args.horizon)))

    if args.backtest:
        results.append(("backtest", verify_backtest(args.region)))

    if args.all_regions:
        _header("7. 전 지역 mock predict 스모크 테스트")
        region_ok = True
        for r in settings.REGIONS:
            try:
                power, weather, indpop = _mock_collectors(r, horizon=3, history_days=30)
                fc = predictor.predict(power, weather, indpop, horizon=3)
                errs = _validate_forecast(fc, r, 3)
                if errs:
                    _fail(r, errs[0])
                    region_ok = False
                else:
                    _ok(r, f"method={fc.method}")
            except Exception as exc:  # noqa: BLE001
                _fail(r, str(exc))
                region_ok = False
        results.append(("all_regions", region_ok))

    # ── 최종 요약 ────────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  최종 결과")
    print("=" * 70)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        mark = PASS if ok else FAIL
        print(f"  {mark}  {name}")

    print(f"\n  {passed}/{total} 섹션 통과")
    if passed == total:
        print(f"\n  {PASS}  예측 파이프라인 검증 완료")
        return 0
    print(f"\n  {FAIL}  일부 섹션 실패 — 위 로그 확인")
    return 1


if __name__ == "__main__":
    sys.exit(main())
