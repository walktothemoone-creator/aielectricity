"""과거 history에서 월별 추세 통계를 산출한다."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict


def monthly_totals(history: list[dict]) -> list[dict]:
    """history → 월별 총수요, 일평균, 전월비 변화율 목록."""
    by_month: dict[str, list[float]] = defaultdict(list)
    for row in history:
        ym = row["date"][:6]  # YYYYMM
        by_month[ym].append(row["demand_mwh"])

    result = []
    prev_total: float | None = None
    for ym in sorted(by_month):
        vals = by_month[ym]
        total = sum(vals)
        avg = total / len(vals)
        mom = round((total - prev_total) / prev_total * 100, 2) if prev_total else None
        result.append({
            "ym": ym,
            "label": f"{ym[:4]}년 {int(ym[4:])}월",
            "total_mwh": round(total, 1),
            "daily_avg_mwh": round(avg, 1),
            "mom_pct": mom,
            "days": len(vals),
        })
        prev_total = total
    return result


def weekly_trend(history: list[dict]) -> list[dict]:
    """history → 주차별 합계 (최근 N주)."""
    if not history:
        return []
    sorted_h = sorted(history, key=lambda x: x["date"])
    weeks: dict[str, float] = defaultdict(float)
    for row in sorted_h:
        d = dt.datetime.strptime(row["date"], "%Y%m%d").date()
        iso = d.isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        weeks[key] += row["demand_mwh"]
    return [{"week": k, "total_mwh": round(v, 1)} for k, v in sorted(weeks.items())]


def ascii_bar_chart(values: list[float], labels: list[str], width: int = 30) -> str:
    """간단한 ASCII 막대 차트를 문자열로 반환한다."""
    if not values:
        return ""
    max_v = max(values) or 1
    lines = []
    for label, val in zip(labels, values):
        bar_len = int(val / max_v * width)
        bar = "█" * bar_len
        lines.append(f"  {label:>12} │{bar:<{width}} {val:,.0f} MWh")
    return "\n".join(lines)


def format_trend_report(monthly: list[dict], region: str) -> str:
    """월별 추세를 사람이 읽기 쉬운 텍스트 블록으로 포맷한다."""
    lines = [f"[수요 추세] {region}", "─" * 60]
    for m in monthly:
        mom_str = ""
        if m["mom_pct"] is not None:
            arrow = "▲" if m["mom_pct"] > 0 else "▼"
            mom_str = f"  {arrow} 전월비 {abs(m['mom_pct']):.1f}%"
        lines.append(
            f"  {m['label']:>14}  합계 {m['total_mwh']:>12,.0f} MWh"
            f"  일평균 {m['daily_avg_mwh']:>8,.0f} MWh{mom_str}"
        )
    lines.append("")
    # 막대 차트
    lines.append(ascii_bar_chart(
        [m["total_mwh"] for m in monthly],
        [m["label"] for m in monthly],
    ))
    return "\n".join(lines)


def format_forecast_report(predictions: list[dict], region: str,
                           forecast_month: int | None = None) -> str:
    """예측 결과를 일자별 + 월별 합계로 포맷한다."""
    if forecast_month:
        target = f"{forecast_month}월"
        preds = [p for p in predictions if int(p["date"][4:6]) == forecast_month]
    else:
        target = f"{len(predictions)}일"
        preds = predictions

    if not preds:
        return f"[{target} 예측] 해당 기간 예측값 없음"

    monthly_total = sum(p["demand_mwh"] for p in preds)
    lower_total   = sum(p["lower"]      for p in preds)
    upper_total   = sum(p["upper"]      for p in preds)
    daily_avg     = monthly_total / len(preds)

    lines = [
        f"[{target} 수요 예측] {region}",
        "─" * 60,
        f"  예측 월 합계   : {monthly_total:>12,.0f} MWh",
        f"  95% CI 하한    : {lower_total:>12,.0f} MWh",
        f"  95% CI 상한    : {upper_total:>12,.0f} MWh",
        f"  일 평균 수요   : {daily_avg:>12,.0f} MWh",
        "",
        f"  {'날짜':>10}  {'예측(MWh)':>12}  {'하한':>10}  {'상한':>10}",
        "  " + "─" * 50,
    ]
    for p in preds:
        d = dt.datetime.strptime(p["date"], "%Y%m%d").strftime("%Y-%m-%d")
        lines.append(
            f"  {d:>10}  {p['demand_mwh']:>12,.0f}  {p['lower']:>10,.0f}  {p['upper']:>10,.0f}"
        )
    return "\n".join(lines)
