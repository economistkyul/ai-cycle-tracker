#!/usr/bin/env python3
"""통합 대시보드 v3 — 상태 영속성·구조 값 평가·override 관측 연결·다자산·매도 계획."""
from __future__ import annotations
import sys
from datetime import date
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.core.observations import load_history, latest_fresh                 # noqa: E402
from src.core.state_store import load_states, save_states, update_state      # noqa: E402
from src.signals.macro import eval_macro, eval_emergency_override            # noqa: E402
from src.signals.technical import eval_all_assets                            # noqa: E402
from src.signals.structural import eval_structural, derive_krw_stage         # noqa: E402
from src.signals.engine import AxisResult, decide                            # noqa: E402
from src.execution.planner import build_plan                                 # noqa: E402
from src.portfolio import risk                                               # noqa: E402

SCHEMA_ONLY_AXES = {"earnings_regime": "fwd EPS 수정률",
                    "valuation_regime": "fwd P/E·ERP",
                    "ai_semiconductor_cycle": "마진/재고/수주"}
STRUCTURAL_INPUTS = ["usdkrw_trend", "foreign_net_flow", "oil_trend",
                     "kr_eps_revision", "restocking_cycle"]


def _cfg(name):
    with open(ROOT / "config" / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fresh_values(history, metrics, today) -> dict:
    out = {}
    for m in metrics:
        e = latest_fresh(history, m, today)
        if e is not None:
            out[m] = e["value"]
    return out


def run(today: date | None = None, persist: bool = True) -> dict:
    today = today or date.today()
    triggers, ma_cfg, regimes = _cfg("triggers.yaml"), _cfg("moving_average.yaml"), _cfg("regimes.yaml")
    pf = risk.load_portfolio()
    risk.validate_weights(pf)
    history = load_history()
    store = load_states()

    # 1) macro — 이전 상태 주입 (hysteresis 실행 간 유지)
    macro = eval_macro(history, triggers, today, prev_states=store)

    # 2) technical — 다자산
    tech = eval_all_assets(ma_cfg, pf["leveraged_etf_rules"], today)
    # 대표 지수: 판정 가능한 지수 중 최악 상태 채택 (보수적)
    order = ["TREND_BREAK", "TREND_WARNING", "PULLBACK", "RECOVERY",
             "EXTENDED", "TREND_STRONG"]
    known_idx = [v["state"] for v in tech["indices"].values() if v["state"] != "UNKNOWN"]
    tech_state = next((s for s in order if s in known_idx), "UNKNOWN")

    # 3) structural — 값 기반 + min_inputs 실사용
    sv = fresh_values(history, STRUCTURAL_INPUTS, today)
    min_in = regimes["axes"]["structural_regime"].get("min_inputs_required", 3)
    st = eval_structural(sv, min_inputs=min_in)

    # 4) KRW stage 유도 + 수기 모순 경고
    manual = fresh_values(history, ["krw_stage_manual"], today).get("krw_stage_manual")
    krw_stage, krw_warn = derive_krw_stage(sv, manual_stage=manual)

    # 5) emergency override — 관측/평가 결과에서 입력 연결 (하드코딩 제거)
    ov_vals = fresh_values(history, ["forward_eps_3m_change_pct",
                                    "hy_spread_widening_bp_20d"], today)
    ov_inputs = {**ov_vals, "technical_regime": tech_state}
    ov_state, ov_reasons = eval_emergency_override(ov_inputs, triggers["emergency_override"])

    axes = {
        "macro_financial_stress": AxisResult("macro", macro["state"], reasons=macro["reasons"]),
        "technical_regime": AxisResult("technical", tech_state,
                                       reasons=[f"지수 판정: " + ", ".join(
                                           f"{k}={v['state']}" for k, v in tech["indices"].items())],
                                       confidence="none" if tech_state == "UNKNOWN" else "normal"),
        "structural_regime": AxisResult("structural", st["state"], reasons=st["reasons"],
                                        confidence=st["confidence"]),
    }
    for ax, needed in SCHEMA_ONLY_AXES.items():
        axes[ax] = AxisResult(ax, "UNKNOWN",
                              reasons=[f"[schema_only] {needed} 데이터 미연결"],
                              confidence="none")

    result = decide(axes, emergency=(ov_state == "FIRED"), emergency_reasons=ov_reasons)
    plan = build_plan(result["final_state"], {k: v.state for k, v in axes.items()},
                      _cfg("sell_sequence.yaml"), krw_stage=krw_stage)

    # 상태 영속화
    for key, sig in macro["signals"].items():
        update_state(store, key, sig.state, sig.reasons[0], today)
    update_state(store, "final", result["final_state"], "; ".join(result["reasons"])[:200], today)
    if persist:
        save_states(store)

    vals, is_demo = risk.load_account_values()
    exposure = risk.combined_exposure(pf, vals, is_demo) if vals else None

    return {"today": today, "macro": macro, "tech": tech, "structural": st,
            "krw_stage": krw_stage, "krw_warn": krw_warn,
            "override": (ov_state, ov_reasons), "result": result, "plan": plan,
            "exposure": exposure, "store": store}


def main():
    r = run()
    res, exp = r["result"], r["exposure"]
    print("=" * 64)
    print(f"  AI CYCLE TRACKER v3   기준일: {r['today']}   [recommendation_only]")
    print("=" * 64)
    for k, v in res["axes"].items():
        print(f"  [{v['state']:<26}] {k} ({v['confidence']})")
        for reason in v["reasons"][:2]:
            print(f"      - {reason}")
    ov_state, _ = r["override"]
    print(f"  [{ov_state:<26}] emergency_override")
    print(f"  KRW stage(유도): {r['krw_stage']}" +
          (f"  ⚠️ {r['krw_warn']}" if r["krw_warn"] else ""))
    print("-" * 64)
    print(f"  최종 상태: {res['final_state']} (수동 승인 필요)")
    for reason in res["reasons"]:
        print(f"  → {reason}")
    active = [s for s in r["plan"]["steps"] if s["active"]]
    print(f"  매도 계획: 활성 스텝 {len(active)}건" +
          ("" if not active else " — " + ", ".join(
              f"{s['bucket']}({s['target_reduction_pct']}%/{s['deadline_days']}일)" for s in active)))
    if exp:
        tag = "  ⚠️ DEMO DATA — 실계좌값 아님 (account_values.yaml 미공급)" if exp["is_demo_data"] else ""
        print("-" * 64 + f"\n  합산 위험{tag}")
        print(f"  실효 노출 {exp['effective_exposure_pct']}% / 베타조정 {exp['beta_adjusted_exposure_pct']}%")
        fn, fe = exp["factor_exposure_nominal_pct"], exp["factor_exposure_effective_pct"]
        print(f"  팩터(명목/레버리지조정): 반도체 {fn['semiconductor']}/{fe['semiconductor']}% · "
              f"나스닥 {fn['nasdaq_megacap']}/{fe['nasdaq_megacap']}% · "
              f"AIcapex {fn['ai_capex']}/{fe['ai_capex']}%")
        print(f"  국가: {exp['country_exposure_pct']} / 통화: {exp['currency_exposure_pct']}")
        t5 = exp["top5_concentration"]
        print(f"  Top5 집중도({t5['basis']} 기준): {t5['value_pct']}%"
              + (f" — {t5.get('note','')}" if t5.get("note") else ""))
        print(f"  중복 종목: {', '.join(exp['overlap_holdings'])}")
        print(f"  레버리지 버킷 가중: {exp['leveraged_weighting']}")
    print("=" * 64)


if __name__ == "__main__":
    main()
