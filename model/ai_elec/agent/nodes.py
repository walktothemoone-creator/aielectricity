"""LangGraph 노드 구현. 각 노드는 ElecState 를 받아 부분 갱신 dict 를 반환한다.

관심사 분리:
  collect_node   — 공공데이터 수집
  predict_node   — AutoGluon 수요 예측
  decision_node  — Bayesian 기대손실 (전략보다 먼저, LLM 에 근거 제공)
  strategy_node  — Gemini SWOT 전략 (실패 시 규칙기반 fallback)
  report_node    — 최종 리포트 텍스트
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json

from ..collectors.industry import IndustryPopulationCollector
from ..collectors.power import PowerCollector
from ..collectors.weather import WeatherCollector
from ..config import settings
from ..decision import bayesian
from ..ml import predictor
from . import prompts


def collect_node(state: dict) -> dict:
    region = state["region"]
    horizon = state.get("horizon_days", 3)
    errors = list(state.get("errors", []))

    weather = WeatherCollector().collect(region=region, days=horizon)
    power = PowerCollector().collect(region=region, history_days=60)
    indpop = IndustryPopulationCollector().collect(region=region)

    return {
        "weather": weather,
        "power": power,
        "indpop": indpop,
        "sources": {
            "weather": weather["source"],
            "power": power["source"],
            "industry_population": indpop["source"],
        },
        "errors": errors,
    }


def predict_node(state: dict) -> dict:
    errors = list(state.get("errors", []))
    try:
        fc = predictor.predict(
            state["power"], state["weather"], state["indpop"],
            horizon=state.get("horizon_days", 3),
        )
        return {"forecast": dataclasses.asdict(fc)}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"predict:{exc}")
        return {"forecast": {"region": state["region"], "horizon_days": 0,
                             "predictions": [], "method": "failed"}, "errors": errors}


def decision_node(state: dict) -> dict:
    errors = list(state.get("errors", []))
    try:
        dec = bayesian.decide(
            state["forecast"]["predictions"],
            state["power"]["data"]["history"],
        )
        return {"decision": dataclasses.asdict(dec)}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"decision:{exc}")
        return {"decision": {"posterior_peak": None, "expected_loss": {},
                             "recommended": "hold", "rationale": "decision failed"},
                "errors": errors}


def strategy_node(state: dict) -> dict:
    errors = list(state.get("errors", []))
    # 1) Gemini 시도
    if settings.GEMINI_API_KEY:
        try:
            return {"strategy": _gemini_strategy(state)}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"strategy_llm:{exc}")
    # 2) 규칙 기반 fallback
    return {"strategy": _rule_based_strategy(state), "errors": errors}


def report_node(state: dict) -> dict:
    fc = state.get("forecast", {})
    dec = state.get("decision", {})
    strat = state.get("strategy", {})
    src = state.get("sources", {})
    region = state.get("region")

    lines = [f"# {region} 전기수요 예측 리포트",
             f"_생성: {dt.datetime.now():%Y-%m-%d %H:%M}_", ""]
    lines.append(f"- 예측 방법: **{fc.get('method')}**  |  데이터 출처: {src}")
    lines.append("")
    lines.append("## 일자별 예측 수요 (MWh)")
    for p in fc.get("predictions", []):
        lines.append(f"- {p['date']}: **{p['demand_mwh']:,.0f}** "
                     f"(95% CI {p['lower']:,.0f} ~ {p['upper']:,.0f})")
    lines.append("")
    lines.append("## 피크 리스크 의사결정 (Bayesian Expected Loss)")
    lines.append(f"- 피크 사후확률 P(peak): **{dec.get('posterior_peak')}**")
    lines.append(f"- 기대손실: {dec.get('expected_loss')}")
    lines.append(f"- 권고 전략: **{bayesian.ACTION_LABEL.get(dec.get('recommended'), dec.get('recommended'))}**")
    lines.append(f"- 근거: {dec.get('rationale')}")
    lines.append("")
    lines.append("## 운영 전략 A/B")
    lines.append(f"> {strat.get('summary','')}")
    for key in ("option_a", "option_b"):
        o = strat.get(key, {})
        lines.append(f"### {o.get('name', key)}")
        for a in o.get("actions", []):
            lines.append(f"- {a}")
        lines.append(f"- _트레이드오프_: {o.get('tradeoff','')}")
    sw = strat.get("swot", {})
    if sw:
        lines.append("")
        lines.append("## SWOT")
        lines.append(f"- S: {sw.get('strength','')}")
        lines.append(f"- W: {sw.get('weakness','')}")
        lines.append(f"- O: {sw.get('opportunity','')}")
        lines.append(f"- T: {sw.get('threat','')}")
    if state.get("errors"):
        lines.append("")
        lines.append(f"> ⚠️ degraded paths: {state['errors']}")
    return {"report": "\n".join(lines)}


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------
def _gemini_strategy(state: dict) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=prompts.STRATEGY_SYSTEM)
    resp = model.generate_content(prompts.build_user_prompt(state))
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.strip("`").lstrip("json").strip()
    return json.loads(text)


def _rule_based_strategy(state: dict) -> dict:
    dec = state.get("decision", {})
    post = dec.get("posterior_peak") or 0.0
    ind = state.get("indpop", {}).get("data", {})
    high_industry = (ind.get("grdp_trillion", 0) or 0) > 100

    if post >= 0.5:
        summary = "피크 사후확률이 높아 선제적 부하관리가 필요합니다."
        a = {"name": "공격적 예비력 확보", "actions": ["예비력 발전 우선 기동", "DR 사전 공지"],
             "tradeoff": "운영비 상승, 정전 리스크 최소화"}
        b = {"name": "수요반응 중심", "actions": ["대형 산업수요 DR 계약 발동", "비핵심 부하 시간이동"],
             "tradeoff": "비용 절감, 일부 미참여 리스크 잔존"}
    else:
        summary = "정상 수요 구간으로 비용 효율 운영이 가능합니다."
        a = {"name": "현상 유지", "actions": ["정규 급전 유지", "실시간 모니터링"],
             "tradeoff": "최저비용, 급변 시 대응 지연"}
        b = {"name": "경량 헤지", "actions": ["부분 예비력 대기", "기상 급변 알림 설정"],
             "tradeoff": "소폭 비용, 변동성 대비"}
    swot = {
        "strength": "고부가 산업 밀집으로 안정적 기저수요" if high_industry else "수요 변동성 낮음",
        "weakness": "냉난방 피크 민감도",
        "opportunity": "DR 자원·재생E 연계 확대",
        "threat": "기상 이변에 따른 급격한 피크",
    }
    return {"summary": summary, "option_a": a, "option_b": b, "swot": swot}
