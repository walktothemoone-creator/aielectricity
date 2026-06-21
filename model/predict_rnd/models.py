"""백테스트 예측 모델 모음.

Model 1 — 단순 선형추세 (기존 fallback)
Model 2 — 피처 기반 OLS 회귀 (numpy, 별도 설치 없이 동작)
Model 3 — AutoGluon (설치 시 자동 사용)

모든 모델은 fit(train_rows) → predict(future_dates) → list[float] 인터페이스.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field


# ────────────────────────────────────────────────────────────────────────────
# 공통 피처 빌더
# ────────────────────────────────────────────────────────────────────────────

def _features(d: dt.date) -> dict:
    doy = d.timetuple().tm_yday
    temp = 13 + 13 * math.sin(2 * math.pi * (doy - 110) / 365)
    return {
        "dow":          float(d.weekday()),
        "doy":          float(doy),
        "is_weekend":   float(d.weekday() >= 5),
        "temp_avg":     temp,
        "cooling_load": max(temp - 24, 0),
        "heating_load": max(2 - temp, 0) + max(0, -temp + 5),
        "sin_doy":      math.sin(2 * math.pi * doy / 365),
        "cos_doy":      math.cos(2 * math.pi * doy / 365),
        "sin2_doy":     math.sin(4 * math.pi * doy / 365),
        "cos2_doy":     math.cos(4 * math.pi * doy / 365),
    }


def _feat_vec(d: dt.date) -> list[float]:
    f = _features(d)
    return [
        1.0,  # intercept
        f["dow"],
        f["is_weekend"],
        f["temp_avg"],
        f["cooling_load"],
        f["heating_load"],
        f["sin_doy"],
        f["cos_doy"],
        f["sin2_doy"],
        f["cos2_doy"],
    ]


# ────────────────────────────────────────────────────────────────────────────
# Model 1: 단순 선형추세
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class LinearTrendModel:
    name: str = "단순선형추세"
    _slope: float = field(default=0.0, init=False)
    _intercept: float = field(default=0.0, init=False)
    _resid_sd: float = field(default=0.0, init=False)

    def fit(self, train_rows: list[dict]) -> "LinearTrendModel":
        ys = [r["demand_mwh"] for r in train_rows]
        n  = len(ys)
        xs = list(range(n))
        mx, my = sum(xs) / n, sum(ys) / n
        denom  = sum((x - mx) ** 2 for x in xs) or 1
        self._slope     = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
        self._intercept = my - self._slope * mx
        self._resid_sd  = (sum((y - (self._slope * x + self._intercept)) ** 2
                               for x, y in zip(xs, ys)) / n) ** 0.5
        self._n_train   = n
        return self

    def predict(self, future_dates: list[dt.date]) -> list[float]:
        preds = []
        for i, d in enumerate(future_dates):
            idx  = self._n_train + i
            base = self._slope * idx + self._intercept
            doy  = d.timetuple().tm_yday
            temp = 13 + 13 * math.sin(2 * math.pi * (doy - 110) / 365)
            cl   = max(temp - 24, 0)
            hl   = max(2 - temp, 0) + max(0, -temp + 5)
            adj  = 1.0 + 0.008 * (cl + hl)
            wk   = 0.92 if d.weekday() >= 5 else 1.0
            preds.append(base * wk * adj)
        return preds


# ────────────────────────────────────────────────────────────────────────────
# Model 2: 피처 기반 OLS (numpy)
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class FeatureOLSModel:
    name: str = "피처OLS회귀"
    _coef: list[float] = field(default_factory=list, init=False)

    def fit(self, train_rows: list[dict]) -> "FeatureOLSModel":
        import numpy as np
        X = np.array([
            _feat_vec(dt.datetime.strptime(r["date"], "%Y%m%d").date())
            for r in train_rows
        ])
        y = np.array([r["demand_mwh"] for r in train_rows])
        # OLS: (XᵀX)⁻¹ Xᵀy  — numpy lstsq로 안정적으로 풀기
        coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        self._coef = coef.tolist()
        return self

    def predict(self, future_dates: list[dt.date]) -> list[float]:
        import numpy as np
        X = np.array([_feat_vec(d) for d in future_dates])
        return (X @ np.array(self._coef)).tolist()


# ────────────────────────────────────────────────────────────────────────────
# Model 3: AutoGluon (선택적)
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class AutoGluonModel:
    name: str = "AutoGluon"
    time_limit: int = 60
    _predictor: object = field(default=None, init=False)

    def fit(self, train_rows: list[dict]) -> "AutoGluonModel":
        import pandas as pd
        from autogluon.tabular import TabularPredictor

        rows = []
        for r in train_rows:
            d = dt.datetime.strptime(r["date"], "%Y%m%d").date()
            f = _features(d)
            f["demand_mwh"] = r["demand_mwh"]
            rows.append(f)

        df = pd.DataFrame(rows)
        feat_cols = [c for c in df.columns if c != "demand_mwh"]
        self._predictor = TabularPredictor(
            label="demand_mwh", problem_type="regression", verbosity=0
        ).fit(df[feat_cols + ["demand_mwh"]], time_limit=self.time_limit, presets="medium_quality")
        self._feat_cols = feat_cols
        return self

    def predict(self, future_dates: list[dt.date]) -> list[float]:
        import pandas as pd
        rows = [_features(d) for d in future_dates]
        df   = pd.DataFrame(rows)
        return self._predictor.predict(df[self._feat_cols]).tolist()


def available_models() -> list:
    """설치 환경에 따라 사용 가능한 모델 목록을 반환한다."""
    models = [LinearTrendModel(), FeatureOLSModel()]
    try:
        import autogluon.tabular  # noqa: F401
        models.append(AutoGluonModel())
    except ImportError:
        pass
    return models
