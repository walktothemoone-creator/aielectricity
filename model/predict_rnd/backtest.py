"""월별 총수요 예측 정확도 백테스트 엔진.

Rolling-origin 방식:
  - 학습 데이터: 목표 월 이전까지의 전체 history
  - 예측 대상:   목표 월 (1일~말일)
  - 정확도 지표: MAPE, RMSE, R²
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field


@dataclass
class MonthResult:
    year: int
    month: int
    model_name: str
    actual_total: float
    predicted_total: float
    actual_daily: list[float]
    predicted_daily: list[float]

    @property
    def mape(self) -> float:
        """월 합계 기준 MAPE (%)."""
        if self.actual_total == 0:
            return float("inf")
        return abs(self.predicted_total - self.actual_total) / self.actual_total * 100

    @property
    def accuracy(self) -> float:
        """정확도 (%) = 100 - MAPE."""
        return max(0.0, 100.0 - self.mape)

    @property
    def daily_mape(self) -> float:
        """일별 MAPE 평균 (%)."""
        errors = []
        for a, p in zip(self.actual_daily, self.predicted_daily):
            if a != 0:
                errors.append(abs(p - a) / a * 100)
        return sum(errors) / len(errors) if errors else float("inf")

    @property
    def rmse(self) -> float:
        n = len(self.actual_daily)
        if n == 0:
            return float("inf")
        return math.sqrt(sum((a - p) ** 2
                             for a, p in zip(self.actual_daily, self.predicted_daily)) / n)

    @property
    def r2(self) -> float:
        ys = self.actual_daily
        mean_y = sum(ys) / len(ys)
        ss_tot = sum((y - mean_y) ** 2 for y in ys) or 1e-9
        ss_res = sum((a - p) ** 2 for a, p in zip(ys, self.predicted_daily))
        return 1 - ss_res / ss_tot


def _month_dates(year: int, month: int) -> list[dt.date]:
    start = dt.date(year, month, 1)
    if month == 12:
        end = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        end = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    out = []
    d = start
    while d <= end:
        out.append(d)
        d += dt.timedelta(days=1)
    return out


def run_backtest(
    all_daily: list[dict],
    target_months: list[tuple[int, int]],
    models: list,
    min_train_days: int = 90,
) -> list[MonthResult]:
    """
    all_daily      : 전체 일자별 데이터 (YYYYMMDD 정렬)
    target_months  : [(year, month), ...] 예: [(2026,1),...,(2026,5)]
    models         : models.py 의 모델 인스턴스 목록
    min_train_days : 학습 최소 일수

    Returns: MonthResult 목록
    """
    # date → demand_mwh 조회용 dict
    data_map = {r["date"]: r["demand_mwh"] for r in all_daily}

    results: list[MonthResult] = []

    for year, month in target_months:
        target_dates = _month_dates(year, month)
        target_start = dt.date(year, month, 1)

        # 학습 데이터: target_start 이전 전체
        train_rows = [
            r for r in all_daily
            if dt.datetime.strptime(r["date"], "%Y%m%d").date() < target_start
        ]
        if len(train_rows) < min_train_days:
            print(f"  [SKIP] {year}년 {month}월: 학습 데이터 부족 ({len(train_rows)}일 < {min_train_days})")
            continue

        # 실제값
        actual_daily = [
            data_map.get(d.strftime("%Y%m%d"), 0.0) for d in target_dates
        ]
        actual_total = sum(actual_daily)

        for model in models:
            try:
                model.fit(train_rows)
                predicted_daily = model.predict(target_dates)
                predicted_total = sum(predicted_daily)

                results.append(MonthResult(
                    year=year,
                    month=month,
                    model_name=model.name,
                    actual_total=round(actual_total, 1),
                    predicted_total=round(predicted_total, 1),
                    actual_daily=actual_daily,
                    predicted_daily=predicted_daily,
                ))
            except Exception as e:
                print(f"  [ERROR] {model.name} / {year}-{month:02d}: {e}")

    return results


def summarize(results: list[MonthResult]) -> dict[str, dict]:
    """모델별 평균 정확도 요약."""
    by_model: dict[str, list[MonthResult]] = {}
    for r in results:
        by_model.setdefault(r.model_name, []).append(r)

    summary = {}
    for model_name, mrs in by_model.items():
        avg_accuracy = sum(m.accuracy for m in mrs) / len(mrs)
        avg_mape     = sum(m.mape     for m in mrs) / len(mrs)
        avg_rmse     = sum(m.rmse     for m in mrs) / len(mrs)
        avg_r2       = sum(m.r2       for m in mrs) / len(mrs)
        summary[model_name] = {
            "avg_accuracy_pct": round(avg_accuracy, 2),
            "avg_mape_pct":     round(avg_mape, 2),
            "avg_rmse":         round(avg_rmse, 1),
            "avg_r2":           round(avg_r2, 4),
            "months":           len(mrs),
            "target_met":       avg_accuracy >= 90.0,
        }
    return summary
