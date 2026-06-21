"""Streamlit 대시보드: 탭1=지역 예측, 탭2=자연어 조회, 탭3=정확도 실험."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import datetime as dt

import pandas as pd
import streamlit as st

from ai_elec.cli import query_parser, trend_analyzer
from ai_elec.collectors.industry import IndustryPopulationCollector
from ai_elec.collectors.power import PowerCollector
from ai_elec.collectors.weather import WeatherCollector
from ai_elec.config import settings
from ai_elec.decision import bayesian
from ai_elec.ml import predictor
from ai_elec.services.agent_service import ElecAgentService

st.set_page_config(page_title="행정구역별 전기수요 예측", layout="wide")


@st.cache_resource
def get_service():
    return ElecAgentService()


st.title("⚡ 행정구역별 일자별 전기수요 예측 에이전트")
st.caption("공공데이터 수집 → AutoGluon 예측 → Bayesian 의사결정 → LLM 전략")

tab1, tab2, tab3 = st.tabs(["📊 지역 예측", "💬 자연어 조회", "🔬 정확도 실험"])


# ══════════════════════════════════════════════════════════════
# TAB 1 — 기존 지역 예측 대시보드
# ══════════════════════════════════════════════════════════════
with tab1:
    col_l, col_r = st.columns([1, 3])
    with col_l:
        region  = st.selectbox("행정구역", settings.region_names(), key="t1_region")
        horizon = st.slider("예측 기간(일)", 1, 7, 3, key="t1_horizon")
        run_t1  = st.button("예측 실행", type="primary", use_container_width=True, key="t1_run")
        st.info("MOCK 모드" if settings.USE_MOCK else "실데이터 모드", icon="🔌")

    if run_t1:
        with st.spinner("공공데이터 수집·예측·전략 도출 중..."):
            result = get_service().run(region, horizon)

        fc    = result["forecast"]
        dec   = result["decision"]
        strat = result["strategy"]

        with col_r:
            st.subheader(f"{region} — 예측 ({fc['method']})")
            preds = fc["predictions"]
            if preds:
                df = pd.DataFrame(preds)
                df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
                st.line_chart(df.set_index("date")[["lower", "demand_mwh", "upper"]])
                st.dataframe(
                    df.assign(**{
                        "예측(MWh)": df["demand_mwh"].map("{:,.0f}".format),
                        "하한": df["lower"].map("{:,.0f}".format),
                        "상한": df["upper"].map("{:,.0f}".format),
                    })[["date", "예측(MWh)", "하한", "상한"]],
                    hide_index=True, use_container_width=True,
                )

            m1, m2, m3 = st.columns(3)
            m1.metric("피크 사후확률", f"{dec.get('posterior_peak')}")
            m2.metric("권고 전략", bayesian.ACTION_LABEL.get(dec.get("recommended"), "-"))
            if dec.get("expected_loss"):
                m3.metric("최소 기대손실", f"{min(dec['expected_loss'].values()):.1f}")

            if dec.get("expected_loss"):
                st.bar_chart(pd.Series(dec["expected_loss"], name="기대손실"))

            st.subheader("운영 전략 A/B")
            st.write(strat.get("summary", ""))
            ca, cb = st.columns(2)
            for c, key in ((ca, "option_a"), (cb, "option_b")):
                o = strat.get(key, {})
                with c:
                    st.markdown(f"**{o.get('name','')}**")
                    for a in o.get("actions", []):
                        st.markdown(f"- {a}")
                    st.caption(f"트레이드오프: {o.get('tradeoff','')}")

        with st.expander("📄 전체 리포트 / 진단"):
            st.markdown(result["report"])
            st.json({"sources": result.get("sources"), "errors": result.get("errors")})
    else:
        with col_r:
            st.write("좌측에서 행정구역과 기간을 선택하고 **예측 실행** 을 누르세요.")


# ══════════════════════════════════════════════════════════════
# TAB 2 — 자연어 조회
# ══════════════════════════════════════════════════════════════
with tab2:
    st.subheader("자연어로 전기수요를 조회하세요")
    st.caption("예: `대구지역 3개월간 수요추세 및 7월 수요예측을 조사해줘`")

    example_queries = [
        "대구지역 3개월간 수요추세 및 7월 수요예측을 조사해줘",
        "서울특별시 2개월 추세와 8월 수요 알려줘",
        "경기도 향후 7일 단기 전력 예측",
        "울산광역시 6개월 수요 트렌드",
    ]

    col_q, col_ex = st.columns([3, 1])
    with col_q:
        nl_query = st.text_input(
            "쿼리 입력",
            placeholder="예: 대구지역 3개월간 수요추세 및 7월 수요예측을 조사해줘",
            key="t2_query",
            label_visibility="collapsed",
        )
    with col_ex:
        selected_ex = st.selectbox("예시 선택", [""] + example_queries,
                                   key="t2_example", label_visibility="collapsed")

    # 예시 선택 시 쿼리 자동 채움
    active_query = selected_ex if selected_ex else nl_query

    run_t2 = st.button("조회", type="primary", key="t2_run")

    if run_t2 and active_query:
        parsed = query_parser.parse(active_query)

        if not parsed["region"]:
            st.error("지역을 인식하지 못했습니다. 지역명을 포함해 다시 입력해주세요.")
            st.stop()

        region_nl      = parsed["region"]
        trend_months   = parsed["trend_months"]
        forecast_month = parsed["forecast_month"]
        forecast_days  = parsed["forecast_days"]
        history_days   = max(trend_months * 31, 90)
        horizon        = (query_parser.horizon_for_month(forecast_month)
                          if forecast_month else forecast_days)
        horizon = max(horizon, 1)

        st.info(
            f"**지역**: {region_nl}  |  "
            f"**추세**: {trend_months}개월  |  "
            f"**예측**: {'%d월 전체' % forecast_month if forecast_month else '향후 %d일' % forecast_days}"
        )

        with st.spinner("데이터 수집 및 예측 중..."):
            power_res  = PowerCollector().collect(region=region_nl, history_days=history_days)
            weather_res = WeatherCollector().collect(region=region_nl, days=min(horizon, 10))
            indpop_res  = IndustryPopulationCollector().collect(region=region_nl)

        # ── 수요 추세 ──────────────────────────────────────────
        st.subheader(f"📈 수요 추세 — 최근 {trend_months}개월")
        history = power_res["data"]["history"]
        monthly = trend_analyzer.monthly_totals(history)
        monthly_disp = monthly[-trend_months:] if len(monthly) >= trend_months else monthly

        if monthly_disp:
            df_m = pd.DataFrame(monthly_disp)
            df_m.index = df_m["label"]
            col_chart, col_table = st.columns([2, 1])
            with col_chart:
                st.bar_chart(df_m["total_mwh"])
            with col_table:
                st.dataframe(
                    df_m[["label", "total_mwh", "daily_avg_mwh", "mom_pct"]].rename(columns={
                        "label": "월", "total_mwh": "합계(MWh)",
                        "daily_avg_mwh": "일평균(MWh)", "mom_pct": "전월비(%)",
                    }),
                    hide_index=True, use_container_width=True,
                )
        else:
            st.warning("추세 데이터가 부족합니다.")

        # ── 수요 예측 ──────────────────────────────────────────
        target_label = f"{forecast_month}월 수요 예측" if forecast_month else f"향후 {forecast_days}일 예측"
        st.subheader(f"🤖 {target_label} — {region_nl}")

        with st.spinner("예측 중..."):
            fc = predictor.predict(power_res, weather_res, indpop_res, horizon=horizon)

        preds_all = fc.predictions
        if forecast_month:
            preds_disp = [p for p in preds_all if int(p["date"][4:6]) == forecast_month]
        else:
            preds_disp = preds_all

        if preds_disp:
            df_p = pd.DataFrame(preds_disp)
            df_p["date"] = pd.to_datetime(df_p["date"], format="%Y%m%d")
            st.line_chart(df_p.set_index("date")[["lower", "demand_mwh", "upper"]])

            total_pred  = sum(p["demand_mwh"] for p in preds_disp)
            total_lower = sum(p["lower"]      for p in preds_disp)
            total_upper = sum(p["upper"]      for p in preds_disp)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("예측 합계(MWh)", f"{total_pred:,.0f}")
            c2.metric("95% CI 하한",    f"{total_lower:,.0f}")
            c3.metric("95% CI 상한",    f"{total_upper:,.0f}")
            c4.metric("일 평균(MWh)",   f"{total_pred/len(preds_disp):,.0f}")

            st.dataframe(
                df_p.assign(**{
                    "예측(MWh)": df_p["demand_mwh"].map("{:,.0f}".format),
                    "하한": df_p["lower"].map("{:,.0f}".format),
                    "상한": df_p["upper"].map("{:,.0f}".format),
                })[["date", "예측(MWh)", "하한", "상한"]],
                hide_index=True, use_container_width=True,
            )
        else:
            st.warning(f"{forecast_month}월 예측값이 없습니다. 예측 기간을 확인하세요.")

        # ── Bayesian 의사결정 ───────────────────────────────────
        st.subheader("📊 피크 리스크 의사결정")
        dec_input = preds_disp if preds_disp else preds_all
        dec = bayesian.decide(dec_input, history)

        d1, d2, d3 = st.columns(3)
        d1.metric("피크 사후확률 P(peak)", f"{dec.posterior_peak:.3f}")
        d2.metric("권고 전략", bayesian.ACTION_LABEL.get(dec.recommended, "-"))
        d3.metric("최소 기대손실", f"{min(dec.expected_loss.values()):.1f}")

        with st.expander("기대손실 상세"):
            st.bar_chart(pd.Series(dec.expected_loss, name="기대손실"))
            st.caption(dec.rationale)

        # ── 데이터 출처 ────────────────────────────────────────
        with st.expander("데이터 출처"):
            st.json({
                "전력": power_res.get("source"),
                "날씨": weather_res.get("source"),
                "산업/인구": indpop_res.get("source"),
                "예측 방법": fc.method,
            })

    elif run_t2:
        st.warning("쿼리를 입력하거나 예시를 선택하세요.")
    else:
        st.write("쿼리를 입력하고 **조회** 버튼을 누르세요.")


# ══════════════════════════════════════════════════════════════
# TAB 3 — 정확도 실험 (predict_rnd)
# ══════════════════════════════════════════════════════════════
with tab3:
    st.subheader("🔬 2026년 1~5월 월별 수요 예측 정확도 실험")
    st.caption("Rolling-origin 백테스트 | 학습: 2025년 | 검증: 2026년 1~5월")

    col_cfg, col_result = st.columns([1, 3])
    with col_cfg:
        exp_region = st.selectbox("지역", settings.region_names(), key="t3_region")
        run_t3 = st.button("실험 실행", type="primary", use_container_width=True, key="t3_run")
        st.info("학습 데이터: 2025-01-01 ~ 목표월 직전\n검증: 2026년 1~5월 각 월 합계")

    with col_result:
        if run_t3:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

            from predict_rnd.data_generator import generate_daily, month_total
            from predict_rnd.models import available_models
            from predict_rnd.backtest import run_backtest, summarize

            cfg = settings.REGIONS[exp_region]
            REF_TODAY   = dt.date(2026, 6, 21)
            train_start = dt.date(2025, 1, 1)
            test_end    = dt.date(2026, 5, 31)

            with st.spinner("합성 데이터 생성 및 백테스트 실행 중..."):
                all_daily = generate_daily(cfg, train_start, test_end, ref_today=REF_TODAY)
                models    = available_models()
                TARGET_MONTHS = [(2026, m) for m in range(1, 6)]
                results   = run_backtest(all_daily, TARGET_MONTHS, models, min_train_days=90)
                summary   = summarize(results)

            st.success(f"백테스트 완료 — {len(all_daily)}일 데이터, 모델 {len(models)}개")

            # ── 모델별 정확도 요약 ─────────────────────────────
            st.subheader("모델별 평균 정확도")
            sum_rows = []
            for name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_accuracy_pct"]):
                sum_rows.append({
                    "모델": name,
                    "평균 정확도(%)": s["avg_accuracy_pct"],
                    "평균 MAPE(%)":   s["avg_mape_pct"],
                    "평균 RMSE":      s["avg_rmse"],
                    "평균 R²":        s["avg_r2"],
                    "90% 달성": "✔" if s["target_met"] else "✘",
                })
            df_sum = pd.DataFrame(sum_rows)
            st.dataframe(df_sum, hide_index=True, use_container_width=True)

            # 90% 달성 여부 배너
            best_model = max(summary, key=lambda k: summary[k]["avg_accuracy_pct"])
            best_acc   = summary[best_model]["avg_accuracy_pct"]
            if best_acc >= 90.0:
                st.success(f"✔ 목표 정확도(90%) 달성! — {best_model}: {best_acc:.2f}%")
            else:
                st.error(f"✘ 목표 미달 — 최고 {best_model}: {best_acc:.2f}% (부족: {90-best_acc:.2f}%)")

            # ── 월별 상세 결과 ─────────────────────────────────
            st.subheader("월별 상세 결과")
            detail_rows = []
            for r in sorted(results, key=lambda x: (x.model_name, x.year, x.month)):
                detail_rows.append({
                    "모델":       r.model_name,
                    "월":         f"{r.year}년 {r.month}월",
                    "실제(MWh)":  f"{r.actual_total:,.0f}",
                    "예측(MWh)":  f"{r.predicted_total:,.0f}",
                    "오차율(%)":  round(r.mape, 2),
                    "정확도(%)":  round(r.accuracy, 2),
                    "R²":         round(r.r2, 4),
                })
            df_detail = pd.DataFrame(detail_rows)
            st.dataframe(df_detail, hide_index=True, use_container_width=True)

            # ── 모델별 정확도 차트 ─────────────────────────────
            st.subheader("모델별 월별 정확도 차트")
            chart_data: dict[str, list] = {}
            months_label = []
            for r in sorted(results, key=lambda x: (x.year, x.month)):
                label = f"{r.month}월"
                if label not in months_label:
                    months_label.append(label)
                chart_data.setdefault(r.model_name, []).append(round(r.accuracy, 2))

            df_chart = pd.DataFrame(chart_data, index=months_label)
            st.line_chart(df_chart)

            # 90% 기준선 표시
            st.caption("* 목표 정확도: 90% 이상")
        else:
            st.write("지역을 선택하고 **실험 실행** 을 누르세요.")
