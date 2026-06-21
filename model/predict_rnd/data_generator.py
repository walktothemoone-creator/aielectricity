"""백테스트용 합성 데이터 생성기.

PowerCollector._synth_history 와 동일한 수식으로 임의 날짜 범위의
일자별 수요를 생성한다. 기준일(today) 고정으로 재현성을 보장한다.
"""
from __future__ import annotations

import datetime as dt
import math


def generate_daily(
    region_cfg: dict,
    start: dt.date,
    end: dt.date,
    ref_today: dt.date | None = None,
) -> list[dict]:
    """
    region_cfg: settings.REGIONS[region] 값 (base_demand_mwh, nx 필요)
    start, end: 생성 날짜 범위 (inclusive)
    ref_today : 노이즈 인덱스 기준일 (None 이면 오늘)

    Returns:
        [{"date": "YYYYMMDD", "demand_mwh": float}, ...]
    """
    base = float(region_cfg["base_demand_mwh"])
    seed = int(region_cfg["nx"])
    ref  = ref_today or dt.date.today()

    out = []
    cursor = start
    while cursor <= end:
        doy      = cursor.timetuple().tm_yday
        seasonal = 1.0 + 0.18 * abs(math.sin(2 * math.pi * (doy - 30) / 365))
        weekday  = 0.92 if cursor.weekday() >= 5 else 1.0
        # 노이즈: ref_today 기준 days-ago 인덱스로 결정론적 생성
        i        = (ref - cursor).days
        noise    = 1.0 + ((seed * abs(i)) % 11 - 5) / 100.0
        val      = base * seasonal * weekday * noise
        out.append({"date": cursor.strftime("%Y%m%d"), "demand_mwh": round(val, 1)})
        cursor += dt.timedelta(days=1)
    return out


def month_total(daily: list[dict], year: int, month: int) -> float:
    """일자별 데이터에서 특정 연월의 합계를 반환한다."""
    return sum(
        r["demand_mwh"]
        for r in daily
        if r["date"][:4] == str(year) and int(r["date"][4:6]) == month
    )
