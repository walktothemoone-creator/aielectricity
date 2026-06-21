"""aielectricity CLI — 자연어 쿼리 기반 전기수요 조회/예측.

사용 예:
    python -m ai_elec.cli.main "대구지역 3개월간 수요추세 및 7월 수요예측을 조사해줘"
    python -m ai_elec.cli.main --region 대구광역시 --trend-months 3 --forecast-month 7
    python -m ai_elec.cli.main --region 서울특별시 --forecast-days 7
    python -m ai_elec.cli.main --list-regions
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ai_elec.cli import query_parser, trend_analyzer
from ai_elec.collectors.power import PowerCollector
from ai_elec.collectors.weather import WeatherCollector
from ai_elec.collectors.industry import IndustryPopulationCollector
from ai_elec.config import settings
from ai_elec.decision import bayesian
from ai_elec.ml import predictor


# ────────────────────────────────────────────────────────────────────────────
# 핵심 실행 로직
# ────────────────────────────────────────────────────────────────────────────

def run_query(
    region: str,
    trend_months: int = 3,
    forecast_month: int | None = None,
    forecast_days: int = 7,
    verbose: bool = False,
) -> None:
    history_days = max(trend_months * 31, 90)

    print()
    print("=" * 62)
    print(f"  ⚡ aielectricity  |  {region}")
    print("=" * 62)
    print(f"  데이터 모드    : {'MOCK' if settings.USE_MOCK else '실데이터'}")
    print(f"  추세 조회 기간 : {trend_months}개월 ({history_days}일)")
    if forecast_month:
        print(f"  예측 대상      : {forecast_month}월 (전체)")
    else:
        print(f"  예측 대상      : 향후 {forecast_days}일")
    print("=" * 62)

    # ── 1. 데이터 수집 ─────────────────────────────────────────
    print("\n📡 공공데이터 수집 중...")
    horizon = query_parser.horizon_for_month(forecast_month) if forecast_month else forecast_days
    horizon = max(horizon, 1)

    power  = PowerCollector().collect(region=region, history_days=history_days)
    weather = WeatherCollector().collect(region=region, days=min(horizon, 10))
    indpop  = IndustryPopulationCollector().collect(region=region)

    pw_src = power.get("source", "")
    wt_src = weather.get("source", "")
    ip_src = indpop.get("source", "")
    print(f"   전력 데이터   : {pw_src}")
    print(f"   날씨 데이터   : {wt_src}")
    print(f"   산업/인구     : {ip_src}")

    # ── 2. 월별 추세 분석 ──────────────────────────────────────
    print()
    history = power["data"]["history"]
    monthly = trend_analyzer.monthly_totals(history)
    # 최근 trend_months 개월만 표시
    monthly_disp = monthly[-trend_months:] if len(monthly) >= trend_months else monthly

    print(trend_analyzer.format_trend_report(monthly_disp, region))

    # ── 3. 수요 예측 ───────────────────────────────────────────
    print()
    print("🤖 수요 예측 중...")
    fc = predictor.predict(power, weather, indpop, horizon=horizon)
    print(f"   예측 방법     : {fc.method}")

    print()
    print(trend_analyzer.format_forecast_report(
        fc.predictions,
        region,
        forecast_month=forecast_month,
    ))

    # ── 4. Bayesian 의사결정 ────────────────────────────────────
    print()
    print("📊 피크 리스크 의사결정")
    print("─" * 62)

    preds_for_decision = fc.predictions
    if forecast_month:
        import datetime as dt
        preds_for_decision = [
            p for p in fc.predictions if int(p["date"][4:6]) == forecast_month
        ] or fc.predictions

    dec = bayesian.decide(preds_for_decision, history)
    print(f"  피크 사후확률  P(peak) = {dec.posterior_peak:.3f}")
    print(f"  기대손실")
    for action, loss in dec.expected_loss.items():
        marker = " ◀ 최적" if action == dec.recommended else ""
        label  = bayesian.ACTION_LABEL.get(action, action)
        print(f"    {label:>18} : {loss:6.2f}{marker}")
    print(f"  권고 전략      : {bayesian.ACTION_LABEL.get(dec.recommended)}")
    print(f"  근거           : {dec.rationale}")

    # ── 5. 피처 중요도 (verbose) ────────────────────────────────
    if verbose and fc.feature_importance:
        print()
        print("🔍 피처 중요도")
        print("─" * 62)
        for feat, imp in sorted(fc.feature_importance.items(),
                                key=lambda x: x[1], reverse=True):
            bar = "█" * int(imp * 30) if isinstance(imp, float) else ""
            print(f"  {feat:>18} : {bar} {imp}")

    print()
    print("=" * 62)
    print("  완료")
    print("=" * 62)
    print()


# ────────────────────────────────────────────────────────────────────────────
# CLI 진입점
# ────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="ai_elec",
        description="행정구역별 전기수요 추세 및 예측 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python -m ai_elec.cli.main "대구지역 3개월간 수요추세 및 7월 수요예측을 조사해줘"
  python -m ai_elec.cli.main --region 대구광역시 --trend-months 3 --forecast-month 7
  python -m ai_elec.cli.main --region 서울특별시 --forecast-days 14
  python -m ai_elec.cli.main --list-regions
        """,
    )
    parser.add_argument("query", nargs="?", help="자연어 쿼리 (예: 대구지역 3개월간 수요추세 및 7월 수요예측)")
    parser.add_argument("--region",         help="행정구역 (직접 지정)")
    parser.add_argument("--trend-months",   type=int, help="추세 조회 개월 수")
    parser.add_argument("--forecast-month", type=int, help="예측 대상 월 (1-12)")
    parser.add_argument("--forecast-days",  type=int, help="단기 예측 일수")
    parser.add_argument("--list-regions",   action="store_true", help="지원 행정구역 목록 출력")
    parser.add_argument("--verbose", "-v",  action="store_true", help="피처 중요도 등 상세 출력")

    args = parser.parse_args(argv)

    if args.list_regions:
        print("\n지원 행정구역 목록:")
        for name in settings.region_names():
            print(f"  - {name}")
        return

    # 자연어 쿼리 파싱
    parsed: dict = {}
    if args.query:
        parsed = query_parser.parse(args.query)
        if not parsed["region"] and not args.region:
            print(f"[오류] 지역을 인식하지 못했습니다: '{args.query}'")
            print("  --region 옵션으로 직접 지정하거나 --list-regions 로 목록을 확인하세요.")
            sys.exit(1)

    # 명시적 인수가 파싱 결과를 덮어씀
    region         = args.region         or parsed.get("region")         or "서울특별시"
    trend_months   = args.trend_months   or parsed.get("trend_months")   or 3
    forecast_month = args.forecast_month or parsed.get("forecast_month")
    forecast_days  = args.forecast_days  or parsed.get("forecast_days")  or 7

    if region not in settings.REGIONS:
        print(f"[오류] 지원하지 않는 지역: {region}")
        print("  --list-regions 로 목록을 확인하세요.")
        sys.exit(1)

    run_query(
        region=region,
        trend_months=trend_months,
        forecast_month=forecast_month,
        forecast_days=forecast_days,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
