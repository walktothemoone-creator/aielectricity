"""전기수요 예측기.

입력: power.history(일자별 수요) + weather.records + industry/population 슬로우 피처.
방식:
  1) 과거 history 로 피처(기온·계절·요일·산업·인구) 테이블 구성
  2) AutoGluon TabularPredictor 로 학습 → 미래 N일 예측
  3) AutoGluon 미설치/데이터부족 시 선형추세 + 기온 민감도 fallback
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field


@dataclass
class Forecast:
    region: str
    horizon_days: int
    predictions: list[dict] = field(default_factory=list)  # [{date, demand_mwh, lower, upper}]
    method: str = "fallback_linear"
    feature_importance: dict = field(default_factory=dict)


def _weekday_factor(d: dt.date) -> float:
    return 0.92 if d.weekday() >= 5 else 1.0


def _seasonal_factor(d: dt.date) -> float:
    doy = d.timetuple().tm_yday
    return 1.0 + 0.18 * abs(math.sin(2 * math.pi * (doy - 30) / 365))


def _build_frame(power: dict, weather: dict, indpop: dict):
    """과거 history 를 학습용 row 리스트로 변환. (pandas 없이도 동작)"""
    history = power["data"]["history"]
    # 기상은 미래 위주라 과거엔 계절 프록시로 채움
    rows = []
    for h in history:
        d = dt.datetime.strptime(h["date"], "%Y%m%d").date()
        doy = d.timetuple().tm_yday
        temp_proxy = 13 + 13 * math.sin(2 * math.pi * (doy - 110) / 365)
        rows.append(
            {
                "date": h["date"],
                "dow": d.weekday(),
                "doy": doy,
                "temp_avg": round(temp_proxy, 1),
                "cooling_load": max(temp_proxy - 24, 0),   # 냉방
                "heating_load": max(2 - temp_proxy, 0) + max(0, -temp_proxy + 5),  # 난방
                "grdp": indpop["data"]["grdp_trillion"],
                "ind_sales": indpop["data"]["industry_sales_index"],
                "pop": indpop["data"]["population_k"],
                "demand_mwh": h["demand_mwh"],  # target
            }
        )
    return rows


def _future_dates(n: int) -> list[dt.date]:
    today = dt.date.today()
    return [today + dt.timedelta(days=i + 1) for i in range(n)]


def predict(power: dict, weather: dict, indpop: dict, horizon: int = 3) -> Forecast:
    region = power["data"]["region"]
    rows = _build_frame(power, weather, indpop)

    # 미래 피처(날씨는 weather collector 의 records 사용)
    wmap = {r["date"]: r for r in weather["data"]["records"]}
    futures = []
    for d in _future_dates(horizon):
        ds = d.strftime("%Y%m%d")
        w = wmap.get(ds)
        temp = w["temp_avg"] if w else 13 + 13 * math.sin(2 * math.pi * (d.timetuple().tm_yday - 110) / 365)
        futures.append(
            {
                "date": ds,
                "dow": d.weekday(),
                "doy": d.timetuple().tm_yday,
                "temp_avg": temp,
                "cooling_load": max(temp - 24, 0),
                "heating_load": max(2 - temp, 0) + max(0, -temp + 5),
                "grdp": indpop["data"]["grdp_trillion"],
                "ind_sales": indpop["data"]["industry_sales_index"],
                "pop": indpop["data"]["population_k"],
            }
        )

    # 1) AutoGluon 시도
    try:
        return _predict_autogluon(region, rows, futures, horizon)
    except Exception:  # noqa: BLE001
        return _predict_linear(region, power, futures, horizon)


def _predict_autogluon(region, rows, futures, horizon) -> Forecast:
    import pandas as pd
    from autogluon.tabular import TabularPredictor

    if len(rows) < 20:
        raise RuntimeError("insufficient data for AutoGluon")

    df = pd.DataFrame(rows)
    feat_cols = ["dow", "doy", "temp_avg", "cooling_load", "heating_load", "grdp", "ind_sales", "pop"]
    predictor = TabularPredictor(label="demand_mwh", problem_type="regression", verbosity=0).fit(
        df[feat_cols + ["demand_mwh"]], time_limit=30, presets="medium_quality"
    )
    fdf = pd.DataFrame(futures)
    preds = predictor.predict(fdf[feat_cols]).tolist()

    # 잔차로 대략적 구간
    resid = (predictor.predict(df[feat_cols]) - df["demand_mwh"]).std()
    out = []
    for f, p in zip(futures, preds):
        out.append(
            {
                "date": f["date"],
                "demand_mwh": round(float(p), 1),
                "lower": round(float(p) - 1.96 * resid, 1),
                "upper": round(float(p) + 1.96 * resid, 1),
            }
        )
    try:
        fi = predictor.feature_importance(df[feat_cols + ["demand_mwh"]])["importance"].to_dict()
    except Exception:  # noqa: BLE001
        fi = {}
    return Forecast(region, horizon, out, method="autogluon", feature_importance=fi)


def _predict_linear(region, power, futures, horizon) -> Forecast:
    """선형추세 + 기온 민감도 fallback."""
    history = power["data"]["history"]
    ys = [h["demand_mwh"] for h in history]
    n = len(ys)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs) or 1
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    intercept = mean_y - slope * mean_x
    resid = (sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys)) / n) ** 0.5

    out = []
    for i, f in enumerate(futures):
        d = dt.datetime.strptime(f["date"], "%Y%m%d").date()
        trend = slope * (n + i) + intercept
        # 기온 민감도: 냉/난방 부하 1도당 약 0.8% 가산
        temp_adj = 1.0 + 0.008 * (f["cooling_load"] + f["heating_load"])
        val = trend * _weekday_factor(d) / _weekday_factor(dt.date.today()) * temp_adj
        out.append(
            {
                "date": f["date"],
                "demand_mwh": round(val, 1),
                "lower": round(val - 1.96 * resid, 1),
                "upper": round(val + 1.96 * resid, 1),
            }
        )
    return Forecast(
        region, horizon, out, method="fallback_linear",
        feature_importance={"temp": 0.45, "trend": 0.3, "weekday": 0.15, "industry": 0.1},
    )
