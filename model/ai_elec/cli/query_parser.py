"""자연어 쿼리 파서.

"대구지역 3개월간 수요추세 및 7월 수요예측을 조사해줘"
→ {region: "대구광역시", trend_months: 3, forecast_month: 7}
"""
from __future__ import annotations

import datetime as dt
import re

from ..config import settings

# 단축 지역명 → 정식 명칭
_ALIASES: dict[str, str] = {
    "서울": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "광주광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도",
    "충북": "충청북도",
    "충남": "충청남도",
    "전북": "전북특별자치도",
    "전남": "전라남도",
    "경북": "경상북도",
    "경남": "경상남도",
    "제주": "제주특별자치도",
}


def parse(query: str) -> dict:
    """
    Returns:
        region         : 행정구역 정식명 (None 이면 인식 실패)
        trend_months   : 추세 확인 개월 수 (기본 3)
        forecast_month : 예측 대상 월 번호 (1-12, None 이면 단기 예측)
        forecast_days  : 단기 예측 일수 (기본 7)
    """
    result: dict = {
        "region": None,
        "trend_months": 3,
        "forecast_month": None,
        "forecast_days": 7,
    }

    # ── 지역 ──────────────────────────────────────────────────
    # 정식 명칭 우선
    for name in sorted(settings.REGIONS, key=len, reverse=True):
        if name in query:
            result["region"] = name
            break
    # 단축명 시도
    if not result["region"]:
        for alias, full in sorted(_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
            if alias in query:
                result["region"] = full
                break

    # ── 추세 개월 ─────────────────────────────────────────────
    m = re.search(r"(\d+)\s*개월", query)
    if m:
        result["trend_months"] = int(m.group(1))

    # ── 예측 대상 월 ──────────────────────────────────────────
    # "7월 수요예측", "8월 전력", "7월간" 등
    m = re.search(r"(\d{1,2})\s*월(?!\s*간)", query)
    if m:
        month = int(m.group(1))
        if 1 <= month <= 12:
            result["forecast_month"] = month

    # ── 단기 예측 일수 ────────────────────────────────────────
    m = re.search(r"(\d+)\s*일", query)
    if m:
        result["forecast_days"] = int(m.group(1))

    return result


def forecast_date_range(forecast_month: int) -> tuple[dt.date, dt.date]:
    """예측 대상 월의 시작·종료 날짜를 반환한다."""
    today = dt.date.today()
    year = today.year if forecast_month >= today.month else today.year + 1
    start = dt.date(year, forecast_month, 1)
    # 월말
    if forecast_month == 12:
        end = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        end = dt.date(year, forecast_month + 1, 1) - dt.timedelta(days=1)
    return start, end


def horizon_for_month(forecast_month: int) -> int:
    """오늘부터 해당 월 말일까지의 일수를 반환한다."""
    _, end = forecast_date_range(forecast_month)
    return (end - dt.date.today()).days + 1
