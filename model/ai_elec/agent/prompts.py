"""LLM(Gemini) 프롬프트 템플릿."""
from __future__ import annotations

STRATEGY_SYSTEM = (
    "당신은 한국 전력계통 수요관리 전략가입니다. "
    "주어진 지역의 일자별 전기수요 예측, 피크 사후확률, 날씨/산업/인구 지표를 바탕으로 "
    "운영 전략 두 가지(A/B)를 SWOT 관점으로 도출하세요. "
    "반드시 아래 JSON 스키마만 출력하고 다른 텍스트/마크다운/코드펜스를 절대 넣지 마세요.\n"
    '{"summary": str, '
    '"option_a": {"name": str, "actions": [str], "tradeoff": str}, '
    '"option_b": {"name": str, "actions": [str], "tradeoff": str}, '
    '"swot": {"strength": str, "weakness": str, "opportunity": str, "threat": str}}'
)


def build_user_prompt(state: dict) -> str:
    fc = state.get("forecast", {})
    dec = state.get("decision", {})
    ind = state.get("indpop", {}).get("data", {})
    w = state.get("weather", {}).get("data", {}).get("records", [])
    return (
        f"지역: {state.get('region')}\n"
        f"예측(향후 {fc.get('horizon_days')}일): {fc.get('predictions')}\n"
        f"예측방법: {fc.get('method')}\n"
        f"피크 사후확률: {dec.get('posterior_peak')}\n"
        f"기대손실: {dec.get('expected_loss')}\n"
        f"베이지안 권고: {dec.get('recommended')}\n"
        f"GRDP(조원): {ind.get('grdp_trillion')}, 산업매출지수: {ind.get('industry_sales_index')}, "
        f"인구(천명): {ind.get('population_k')}, 인구증감률%: {ind.get('population_yoy_pct')}\n"
        f"날씨: {w}\n"
        "위 정보를 해석해 전략 A/B 를 도출하세요."
    )
