"""Bayesian Expected Loss 의사결정.

상태(state): 내일 수요가 '피크(고부하)' 인가 '정상' 인가.
  - 사전확률 P(peak): 계절(여름/겨울) 베이스.
  - 우도(likelihood): 예측 수요가 과거 분포의 상위 분위를 얼마나 초과하는가(기온/예비율 신호).
  - 사후확률 P(peak | evidence) ∝ 우도 × 사전.

전략(action):
  A) hold        — 추가조치 없음 (저비용, 그러나 피크 시 정전/페널티 위험)
  B) demand_resp — 수요반응(DR) 발동 (중간비용, 피크 리스크 완화)
  C) ramp_supply — 발전 증설/예비력 확보 (고비용, 피크 리스크 강하게 완화)

손실표 L(action, state) 하에서 기대손실 E[L|a] = Σ_s P(s) L(a,s) 최소 전략 선택.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass
class Decision:
    posterior_peak: float
    expected_loss: dict[str, float]
    recommended: str
    rationale: str


# 손실표 (단위: 상대 비용). 행=전략, 열=상태
LOSS = {
    "hold":        {"peak": 100.0, "normal": 0.0},
    "demand_resp": {"peak": 35.0,  "normal": 12.0},
    "ramp_supply": {"peak": 20.0,  "normal": 30.0},
}

ACTION_LABEL = {
    "hold": "현상 유지(무조치)",
    "demand_resp": "수요반응(DR) 발동",
    "ramp_supply": "예비력/발전 증설",
}


def _seasonal_prior(today: dt.date) -> float:
    """여름(7~8)·겨울(12~1) 피크 사전확률 상향."""
    m = today.month
    if m in (7, 8, 12, 1):
        return 0.45
    if m in (6, 9, 2):
        return 0.30
    return 0.15


def decide(forecast_preds: list[dict], history: list[dict], today: dt.date | None = None) -> Decision:
    today = today or dt.date.today()
    prior = _seasonal_prior(today)

    hist_vals = [h["demand_mwh"] for h in history]
    hist_mean = sum(hist_vals) / len(hist_vals)
    hist_sd = (sum((v - hist_mean) ** 2 for v in hist_vals) / len(hist_vals)) ** 0.5 or 1.0

    # 예측 horizon 의 최대 수요로 z-score → 우도 비율
    peak_pred = max(p["demand_mwh"] for p in forecast_preds)
    z = (peak_pred - hist_mean) / hist_sd

    # 우도: peak 상태일 때 z 가 클 가능성 ↑ (로지스틱), normal 은 반대
    like_peak = 1 / (1 + pow(2.718281828, -(z - 1.0)))   # z>1 부근에서 급상승
    like_normal = 1 - like_peak

    num = like_peak * prior
    den = num + like_normal * (1 - prior)
    posterior = num / den if den else prior

    # 기대손실
    p_state = {"peak": posterior, "normal": 1 - posterior}
    exp_loss = {
        a: round(sum(p_state[s] * LOSS[a][s] for s in p_state), 2) for a in LOSS
    }
    best = min(exp_loss, key=exp_loss.get)

    rationale = (
        f"사전 P(peak)={prior:.2f}, 예측피크 z={z:.2f} → 사후 P(peak)={posterior:.2f}. "
        f"기대손실 최소 전략은 '{ACTION_LABEL[best]}' (E[L]={exp_loss[best]})."
    )
    return Decision(round(posterior, 3), exp_loss, best, rationale)
