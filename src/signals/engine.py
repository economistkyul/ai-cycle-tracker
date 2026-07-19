"""통합 의사결정 엔진 — 6축 독립 평가 → 최종 상태.

원칙 (config/regimes.yaml decision_principles):
A 집중도 단독 매도 금지 / B 이탈 시 레버리지 우선 축소 / C 취약한 집중 승격
D 매크로 삼중 악화 / E emergency override / F 누락 → UNKNOWN
출력은 recommendation_only — 자동 주문 없음.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class AxisResult:
    axis: str
    state: str
    score: float | None = None
    reasons: list[str] = field(default_factory=list)
    confidence: str = "normal"     # normal | low | none


CRITICAL_AXES = ["macro_financial_stress", "technical_regime", "earnings_regime"]


def decide(axes: dict[str, AxisResult], emergency: bool = False,
           emergency_reasons: list[str] | None = None) -> dict:
    """최종 상태 + 원인 설명. 단일 boolean 금지."""
    reasons: list[str] = []
    a = {k: v.state for k, v in axes.items()}

    unknown_critical = [k for k in CRITICAL_AXES if a.get(k, "UNKNOWN") == "UNKNOWN"]

    if emergency:                                                    # 원칙 E
        return _out("EXITING", axes,
                    ["EMERGENCY OVERRIDE: 금리 하락형 붕괴 조건 충족"] + (emergency_reasons or []))

    if a.get("macro_financial_stress") == "FIRED":
        reasons.append("듀얼 매크로 트리거 FIRED → 매도 시퀀싱 개시")
        return _out("EXITING", axes, reasons)

    if len(unknown_critical) >= 2:                                   # 원칙 F
        reasons.append(f"핵심 축 데이터 누락: {unknown_critical} → 판정 보류")
        return _out("UNKNOWN", axes, reasons)

    macro_armed = a.get("macro_financial_stress") == "ARMED"
    trend_break = a.get("technical_regime") in ("TREND_BREAK", "TREND_WARNING")
    structural_bull = a.get("structural_regime") in ("STRUCTURAL_BULL", "BULL_WITH_LATE_CYCLE_RISK")
    fragile = a.get("earnings_regime") == "MULTIPLE_ONLY_RALLY" or \
              a.get("valuation_regime") == "EXPENSIVE_FRAGILE"

    if macro_armed and a.get("technical_regime") == "TREND_BREAK":
        reasons.append("macro ARMED + 추세 붕괴 → 방어 전환")
        return _out("DEFENSIVE", axes, reasons)
    if trend_break and structural_bull:                              # 원칙 B
        reasons.append("구조 강세 유지 중 50일선 이탈 → 현물 아닌 레버리지/고베타 우선 축소")
        return _out("REDUCE_LEVERAGE", axes, reasons)
    if trend_break:
        reasons.append("추세 이탈 (구조 국면 불명) → 방어")
        return _out("DEFENSIVE", axes, reasons)
    if fragile:                                                      # 원칙 C
        reasons.append("가격-이익 괴리 (multiple-only rally / 취약 밸류) → 헤지 동반 보유")
        return _out("HOLD_WITH_HEDGE", axes, reasons)
    if macro_armed:
        reasons.append("macro ARMED — 임계 근접, 레버리지 룰 점검하며 보유")
        return _out("HOLD_WITH_HEDGE", axes, reasons)
    if a.get("technical_regime") == "EXTENDED":
        reasons.append("추세 유지되나 이격 과열 — 신규 매수 자제")
        return _out("RISK_ON_EXTENDED", axes, reasons)
    if a.get("technical_regime") == "UNKNOWN" or a.get("earnings_regime") == "UNKNOWN":
        reasons.append("일부 축 데이터 없음 — 제한적 판정")
        return _out("HOLD_WITH_HEDGE", axes, reasons)
    reasons.append("구조/이익/추세 정합 — 리스크온 유지")
    return _out("RISK_ON", axes, reasons)


def _out(final: str, axes: dict, reasons: list[str]) -> dict:
    return {
        "final_state": final,
        "recommendation_only": True,
        "requires_manual_approval": True,
        "axes": {k: {"state": v.state, "reasons": v.reasons, "confidence": v.confidence}
                 for k, v in axes.items()},
        "reasons": reasons,
    }
