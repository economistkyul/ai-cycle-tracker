"""매도 계획 산출기 — sell_sequence.yaml을 실행 가능한 계획으로 변환.

recommendation_only: 자동 주문 없음. 모든 스텝은 수동 승인 필요.

우선순위 (rule_based_first 100% vs 개별 ETF 50% 축소):
- 개별 ETF reduction_rule(50%)은 '상시' tactical 룰 — 기술적 조건 발생 즉시 권고
- rule_based_first(100%)는 REDUCE_LEVERAGE 이상 상태에서 발동하는 상위 룰
- 둘이 동시에 성립하면 더 큰 감축률(100%)이 우선한다
"""
from __future__ import annotations

ACTIVATION = {   # 최종 상태 → 활성화되는 시퀀스 order
    "EXITING": [1, 2, 3, 4], "DEFENSIVE": [1],
    "REDUCE_LEVERAGE": [], "HOLD_WITH_HEDGE": [], "RISK_ON": [],
    "RISK_ON_EXTENDED": [], "UNKNOWN": [],
}
RULE_BASED_ACTIVE_STATES = {"REDUCE_LEVERAGE", "DEFENSIVE", "EXITING"}


def build_plan(final_state: str, axis_states: dict, seq_cfg: dict,
               krw_stage: int | None = None) -> dict:
    steps = []
    rb = seq_cfg["rule_based_first"]
    steps.append({
        "bucket": "rule_based", "order": 0,
        "target_reduction_pct": rb["target_reduction_pct"],
        "deadline_days": rb["deadline_days"],
        "condition": rb["trigger"],
        "active": final_state in RULE_BASED_ACTIVE_STATES,
        "note": "개별 ETF 50% tactical 룰과 동시 성립 시 100%가 우선",
    })
    active_orders = ACTIVATION.get(final_state, [])
    for s in seq_cfg["sequence"]:
        steps.append({
            "bucket": s["bucket"], "order": s["order"],
            "target_reduction_pct": s["target_reduction_pct"],
            "deadline_days": s["deadline_days"],
            "condition": s["confirm_condition"],
            "expected_cash_pct_after": s.get("cash_target_pct_after"),
            "active": s["order"] in active_orders,
        })
    if krw_stage == 3:
        ov = seq_cfg["krw_override"]
        steps.append({"bucket": "KR_positions", "order": -1,
                      "target_reduction_pct": ov["target_reduction_pct"],
                      "deadline_days": ov["deadline_days"],
                      "condition": ov["condition"], "active": True,
                      "note": "시퀀스 무관 선행 매도"})
    return {"final_state": final_state, "steps": steps,
            "recommendation_only": True, "requires_manual_approval": True,
            "approval_method": seq_cfg.get("approval", {}).get("method", "수기 확인")}
