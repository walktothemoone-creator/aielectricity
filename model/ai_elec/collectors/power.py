"""전력거래소 collector.

- 시간별 전국 전력수요량(15065266, odcloud) — 과거 일자별 수요 history
- (선택) 오늘전력수급현황 — 실시간 스냅샷 (별도 활용신청 필요)

전국 시계열을 지역 베이스라인 비중으로 분배해 지역별 일자 수요 프록시를 만든다.
"""
from __future__ import annotations

import datetime as dt
import math

from ..config import settings
from .base import BaseCollector, cached_get

_HOUR_COLS = [f"{h}시" for h in range(1, 25)]


def _daily_mwh(row: dict) -> float:
    """시간별 MW 합 → 일일 MWh (1시간×MW = MWh)."""
    total = 0.0
    for col in _HOUR_COLS:
        val = row.get(col)
        if val is not None:
            total += float(val)
    return round(total, 1)


def _fetch_nationwide_daily(limit: int = 366) -> list[dict]:
    """odcloud 15065266 — 전국 일별 수요 시계열."""
    per_page = 100
    pages = max(1, math.ceil(limit / per_page))
    rows: list[dict] = []
    for page in range(1, pages + 1):
        raw = cached_get(
            settings.API["kpx_hourly_demand"],
            {
                "serviceKey": settings.DATA_GO_KR_KEY,
                "page": page,
                "perPage": per_page,
            },
        )
        batch = raw.get("data") or []
        rows.extend(r for r in batch if r and r.get("날짜"))
        if len(batch) < per_page:
            break
    out = []
    for row in rows:
        date_raw = str(row["날짜"]).replace("-", "")
        out.append({"date": date_raw, "demand_mwh": _daily_mwh(row)})
    out.sort(key=lambda x: x["date"])
    return out[-limit:]


class PowerCollector(BaseCollector):
    name = "power"

    def fetch(self, region: str, history_days: int = 60, **_) -> dict:
        nationwide = _fetch_nationwide_daily(limit=366)
        if not nationwide:
            raise ValueError("odcloud 전력수요 데이터 없음")

        share = self._region_share(region)
        history = [
            {
                "date": row["date"],
                "demand_mwh": round(row["demand_mwh"] * share, 1),
            }
            for row in nationwide[-history_days:]
        ]

        latest = nationwide[-1]
        nationwide_now = round(latest["demand_mwh"] / 24, 1)  # 일평균 MW 프록시
        nationwide_peak = round(max(latest["demand_mwh"] / 12, nationwide_now), 1)

        return {
            "region": region,
            "nationwide_current_mw": nationwide_now,
            "nationwide_peak_mw": nationwide_peak,
            "region_share": share,
            "history": history,
        }

    def mock(self, region: str, history_days: int = 60, **_) -> dict:
        return {
            "region": region,
            "nationwide_current_mw": 72000.0,
            "nationwide_peak_mw": 81000.0,
            "region_share": self._region_share(region),
            "history": self._synth_history(region, history_days),
        }

    # ------------------------------------------------------------------
    def _region_share(self, region: str) -> float:
        total = sum(m["base_demand_mwh"] for m in settings.REGIONS.values())
        return round(settings.REGIONS[region]["base_demand_mwh"] / total, 4)

    def _synth_history(self, region: str, n: int, scale: float | None = None) -> list[dict]:
        """과거 n일 일자별 수요 시계열 생성(추세+주간+계절+노이즈, 결정론적)."""
        base = settings.REGIONS[region]["base_demand_mwh"]
        seed = settings.REGIONS[region]["nx"]
        today = dt.date.today()
        out = []
        for i in range(n, 0, -1):
            d = today - dt.timedelta(days=i)
            doy = d.timetuple().tm_yday
            seasonal = 1.0 + 0.18 * abs(math.sin(2 * math.pi * (doy - 30) / 365))
            weekday = 0.92 if d.weekday() >= 5 else 1.0
            noise = 1.0 + ((seed * i) % 11 - 5) / 100.0
            val = base * seasonal * weekday * noise
            out.append({"date": d.strftime("%Y%m%d"), "demand_mwh": round(val, 1)})
        return out
