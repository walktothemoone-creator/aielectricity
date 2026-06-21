"""2026년 1~5월 월별 전력수요 예측 정확도 실험.

실행:
    cd model
    python3 -m predict_rnd.run_experiment
    python3 -m predict_rnd.run_experiment --region 경기도
    python3 -m predict_rnd.run_experiment --region 대구광역시 --save-csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from predict_rnd.data_generator import generate_daily, month_total
from predict_rnd.models import available_models
from predict_rnd.backtest import run_backtest, summarize

from ai_elec.config import settings


# ────────────────────────────────────────────────────────────────────────────
# 출력 헬퍼
# ────────────────────────────────────────────────────────────────────────────

PASS = "\033[32m✔\033[0m"
FAIL = "\033[31m✘\033[0m"
SEP  = "─" * 72


def _header(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print("=" * 72)


def _print_monthly_table(results: list, model_name: str) -> None:
    print(f"\n  [{model_name}] 월별 상세 결과")
    print(f"  {'월':>8}  {'실제(MWh)':>14}  {'예측(MWh)':>14}  {'오차율%':>8}  {'정확도%':>8}  {'R²':>7}")
    print("  " + SEP)
    for r in sorted(results, key=lambda x: (x.year, x.month)):
        mark = PASS if r.accuracy >= 90 else FAIL
        print(
            f"  {r.year}년{r.month:>2d}월  "
            f"{r.actual_total:>14,.0f}  "
            f"{r.predicted_total:>14,.0f}  "
            f"{r.mape:>8.2f}  "
            f"{r.accuracy:>7.2f}  "
            f"{r.r2:>7.4f}  {mark}"
        )


def _print_summary(summary: dict) -> None:
    print(f"\n  {'모델':>18}  {'평균정확도%':>10}  {'평균MAPE%':>10}  {'평균RMSE':>10}  {'평균R²':>7}  {'90%달성':>7}")
    print("  " + SEP)
    for model_name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_accuracy_pct"]):
        mark = PASS if s["target_met"] else FAIL
        print(
            f"  {model_name:>18}  "
            f"{s['avg_accuracy_pct']:>10.2f}  "
            f"{s['avg_mape_pct']:>10.2f}  "
            f"{s['avg_rmse']:>10.1f}  "
            f"{s['avg_r2']:>7.4f}  "
            f"  {mark}"
        )


# ────────────────────────────────────────────────────────────────────────────
# 메인 실험
# ────────────────────────────────────────────────────────────────────────────

def run(region: str, save_csv: bool = False) -> None:
    cfg = settings.REGIONS.get(region)
    if not cfg:
        print(f"[오류] 지원하지 않는 지역: {region}")
        sys.exit(1)

    _header(f"2026년 1~5월 전력수요 예측 정확도 실험  |  {region}")

    # ── 합성 데이터 생성 ─────────────────────────────────────
    # 학습: 2025-01-01 ~ 2025-12-31 (1년)
    # 검증: 2026-01-01 ~ 2026-05-31 (5개월)
    REF_TODAY = dt.date(2026, 6, 21)
    train_start = dt.date(2025, 1, 1)
    test_end    = dt.date(2026, 5, 31)

    print(f"\n  데이터 생성 중... (기준일: {REF_TODAY})")
    all_daily = generate_daily(cfg, train_start, test_end, ref_today=REF_TODAY)
    print(f"  전체 {len(all_daily)}일 데이터 생성 완료 ({train_start} ~ {test_end})")

    # ── 실제값 확인 ───────────────────────────────────────────
    print(f"\n  [실제값] 2026년 1~5월 월별 합계")
    print(f"  {'월':>8}  {'합계(MWh)':>14}  {'일수':>6}")
    print("  " + "─" * 36)
    TARGET_MONTHS = [(2026, m) for m in range(1, 6)]
    for year, month in TARGET_MONTHS:
        total = month_total(all_daily, year, month)
        days  = sum(1 for r in all_daily if r["date"][:6] == f"{year}{month:02d}")
        print(f"  {year}년{month:>2d}월  {total:>14,.0f}  {days:>6}일")

    # ── 모델 학습 및 백테스트 ─────────────────────────────────
    models = available_models()
    print(f"\n  실험 모델: {', '.join(m.name for m in models)}")
    print(f"  최소 학습 데이터: 90일\n")

    results = run_backtest(
        all_daily=all_daily,
        target_months=TARGET_MONTHS,
        models=models,
        min_train_days=90,
    )

    # ── 결과 출력 ─────────────────────────────────────────────
    by_model: dict[str, list] = {}
    for r in results:
        by_model.setdefault(r.model_name, []).append(r)

    for model_name, mrs in by_model.items():
        _print_monthly_table(mrs, model_name)

    _header("종합 정확도 요약")
    summary = summarize(results)
    _print_summary(summary)

    # ── 결론 ──────────────────────────────────────────────────
    best_model = max(summary, key=lambda k: summary[k]["avg_accuracy_pct"])
    best_acc   = summary[best_model]["avg_accuracy_pct"]
    print(f"\n  최고 성능 모델 : {best_model}")
    print(f"  평균 정확도    : {best_acc:.2f}%")

    if best_acc >= 90.0:
        print(f"\n  {PASS}  목표 정확도(90%) 달성!")
    else:
        gap = 90.0 - best_acc
        print(f"\n  {FAIL}  목표 정확도 미달 (부족분 {gap:.2f}%)")
        print(f"       → 학습 기간 연장, 더 많은 피처 추가를 권장합니다.")

    # ── CSV 저장 ──────────────────────────────────────────────
    if save_csv:
        out_path = Path(__file__).parent / "results" / f"backtest_{region.replace(' ','_')}.csv"
        out_path.parent.mkdir(exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["model", "year", "month", "actual_mwh", "predicted_mwh",
                        "mape_pct", "accuracy_pct", "daily_mape_pct", "rmse", "r2"])
            for r in results:
                w.writerow([
                    r.model_name, r.year, r.month,
                    round(r.actual_total, 1), round(r.predicted_total, 1),
                    round(r.mape, 4), round(r.accuracy, 4),
                    round(r.daily_mape, 4), round(r.rmse, 2), round(r.r2, 6),
                ])
        print(f"\n  CSV 저장 완료: {out_path}")

    print("\n" + "=" * 72)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="월별 전력수요 예측 정확도 백테스트")
    parser.add_argument("--region",   default="대구광역시", choices=list(settings.REGIONS.keys()))
    parser.add_argument("--save-csv", action="store_true")
    args = parser.parse_args()
    run(region=args.region, save_csv=args.save_csv)
