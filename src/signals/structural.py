"""구조 국면 평가 — 데이터 '존재'가 아니라 '값'을 평가한다.

v2 결함: 입력이 존재하기만 하면 강세를 반환 → weakening+selling도 BULL로 판정됐음.
v3: 값의 방향성 채점 + min_inputs_required 실사용 + 하드 베어 룰.
"""
from __future__ import annotations

POSITIVE = {"usdkrw_trend": "stable_or_strengthening", "foreign_net_flow": "buying",
            "oil_trend": "falling_or_stable", "kr_eps_revision": "rising",
            "restocking_cycle": "expanding"}
NEGATIVE = {"usdkrw_trend": "weakening", "foreign_net_flow": "selling",
            "oil_trend": "rising", "kr_eps_revision": "falling",
            "restocking_cycle": "contracting"}


def eval_structural(values: dict, min_inputs: int = 3) -> dict:
    """values: {metric: value(str)} — 신선 검증을 통과한 값만 전달할 것."""
    known = {k: v for k, v in values.items() if k in POSITIVE and v is not None}
    reasons = []
    if len(known) < min_inputs:
        return {"state": "UNKNOWN", "confidence": "none",
                "reasons": [f"구조 입력 {len(known)}/{min_inputs}개 — 판정 불가"]}

    # 하드 룰: 원화 약세 + 외인 순매도 → 강세 반환 금지
    if known.get("usdkrw_trend") == NEGATIVE["usdkrw_trend"] and \
       known.get("foreign_net_flow") == NEGATIVE["foreign_net_flow"]:
        return {"state": "STRUCTURAL_BEAR", "confidence": "normal",
                "reasons": ["하드 룰: 원화 약세 + 외국인 순매도 동시 발생"]}

    pos = sum(1 for k, v in known.items() if POSITIVE.get(k) == v)
    neg = sum(1 for k, v in known.items() if NEGATIVE.get(k) == v)
    score = pos - neg
    reasons.append(f"방향 채점: +{pos}/-{neg} (입력 {len(known)}개: "
                   + ", ".join(f"{k}={v}" for k, v in known.items()) + ")")

    if score <= -2:
        state = "STRUCTURAL_BEAR"
    elif score < 0:
        state = "NEUTRAL"
    elif score >= 3 and neg == 0 and len(known) >= 4:
        state = "STRUCTURAL_BULL"
    elif score >= 1:
        state = "BULL_WITH_LATE_CYCLE_RISK"
        if len(known) == min_inputs:
            reasons.append("입력이 최소 요건 — STRUCTURAL_BULL 승격 보류")
    else:
        state = "NEUTRAL"
    conf = "low" if len(known) <= min_inputs else "normal"
    return {"state": state, "confidence": conf, "reasons": reasons}


def derive_krw_stage(values: dict, manual_stage: int | None = None) -> tuple[int | None, str | None]:
    """KRW stage 1~3 자동 산출. 수기 override와 모순 시 경고 반환."""
    krw, flow = values.get("usdkrw_trend"), values.get("foreign_net_flow")
    eps = values.get("kr_eps_revision")
    if krw == "weakening" and flow == "selling":
        derived = 3
    elif krw == "stable_or_strengthening" and eps == "decelerating":
        derived = 2
    elif krw == "stable_or_strengthening":
        derived = 1
    else:
        derived = None
    warn = None
    if manual_stage is not None and derived is not None and manual_stage != derived:
        warn = f"수기 stage {manual_stage} ↔ 유도 stage {derived} 모순 — 유도값 우선, 입력 재검토 필요"
    return derived, warn
