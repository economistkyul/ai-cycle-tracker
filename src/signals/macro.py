"""매크로 트리거 엔진 v3.

v3 수정:
- confirm_obs는 스냅샷 수가 아닌 고유 관측/발표 수 (confirm_series)
- confirm_unit: 'trading_day'(일일 금리) / 'release'(월간 CPI) 분리
- emergency override 삼중상태: FIRED / NOT_FIRED / UNKNOWN (입력 누락 ≠ 미충족)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date

from src.core.observations import confirm_series, series, is_fresh


@dataclass
class SignalEval:
    name: str
    state: str
    current: float | None = None
    fire_threshold: float | None = None
    severity: bool = False
    reasons: list[str] = field(default_factory=list)


def eval_threshold_signal(history: list[dict], metric: str, cfg: dict,
                          today: date, prev_state: str = "CLEAR") -> SignalEval:
    name = cfg.get("name", metric)
    unit = cfg.get("confirm_unit", "trading_day")
    s = confirm_series(history, metric, unit, today)   # 유효+중복제거+정렬
    if not s or not is_fresh(s[-1], today):
        return SignalEval(name, "UNKNOWN", reasons=[f"{metric}: 유효 데이터 없음/노후"])

    fire, clear = cfg["fire_threshold"], cfg["clear_threshold"]
    confirm, clear_confirm = int(cfg.get("confirm_obs", 1)), int(cfg.get("clear_confirm_obs", 1))
    values = [x["value"] for x in s]
    cur = values[-1]
    unit_label = "발표" if unit == "release" else "거래일"

    fired_now = len(values) >= confirm and all(v >= fire for v in values[-confirm:])
    cleared_now = len(values) >= clear_confirm and all(v <= clear for v in values[-clear_confirm:])

    if prev_state == "FIRED":
        if cleared_now:
            state, reason = "CLEAR", f"{name}: hysteresis 해제 ({clear} 이하 {clear_confirm}{unit_label} 확인)"
        else:
            state, reason = "FIRED", f"{name}: FIRED 유지 (해제조건 미충족 — 현재 {cur})"
    elif fired_now:
        state, reason = "FIRED", f"{name}: {fire} 이상 고유 {unit_label} {confirm}회 연속 확인"
    elif cur >= fire:
        state, reason = "ARMED", f"{name}: 임계 상회하나 고유 {unit_label} {confirm}회 미충족 " \
                                 f"(유효 {len(values)}건)"
    elif cur >= fire * float(cfg.get("armed_proximity", 0.95)):
        state, reason = "ARMED", f"{name}: 임계 근접 (현재 {cur} / 트리거 {fire})"
    else:
        state, reason = "CLEAR", f"{name}: 여유 {fire - cur:+.2f}"

    return SignalEval(name, state, cur, fire,
                      severity=cur >= cfg.get("severity_threshold", float("inf")),
                      reasons=[reason])


def rate_velocity_flag(history: list[dict], cfg: dict, today: date) -> bool:
    s = [x["value"] for x in confirm_series(history, "us10y", "trading_day", today)]
    w = int(cfg.get("window_obs", 4))
    if len(s) < w:
        return False
    return (s[-1] - s[-w]) * 100 >= float(cfg.get("fast_rise_bp", 40))


def eval_macro(history: list[dict], triggers: dict, today: date,
               prev_states: dict | None = None) -> dict:
    prev = prev_states or {}
    us10y = eval_threshold_signal(history, "us10y", triggers["primary"]["us10y"],
                                  today, prev.get("us10y", {}).get("state", "CLEAR"))
    cpi = eval_threshold_signal(history, "core_cpi", triggers["primary"]["core_cpi"],
                                today, prev.get("core_cpi", {}).get("state", "CLEAR"))
    fast = rate_velocity_flag(history, triggers.get("rate_velocity", {}), today)

    parts = [us10y, cpi]
    if any(p.state == "UNKNOWN" for p in parts):
        overall = "UNKNOWN"
    elif triggers.get("dual_condition_required", True):
        overall = "FIRED" if all(p.state == "FIRED" for p in parts) else \
                  ("ARMED" if any(p.state in ("ARMED", "FIRED") for p in parts) else "CLEAR")
    else:
        overall = "FIRED" if any(p.state == "FIRED" for p in parts) else "CLEAR"

    reasons = [r for p in parts for r in p.reasons]
    if fast:
        reasons.append("금리 상승 속도 경보 (+40bp/4거래일)")
    return {"state": overall, "signals": {"us10y": us10y, "core_cpi": cpi},
            "fast_rates": fast, "reasons": reasons}


def eval_emergency_override(inputs: dict, cfg: dict) -> tuple[str, list[str]]:
    """삼중상태: FIRED / NOT_FIRED / UNKNOWN.

    - 전 조건 판정 가능 + 전부 충족 → FIRED
    - 전 조건 판정 가능 + 하나라도 명시적 미충족 → NOT_FIRED
    - 입력 누락으로 판정 불가 조건 존재 + 나머지가 전부 충족 → UNKNOWN
      (누락을 미충족으로 취급하지 않는다)
    """
    conds, reasons = cfg.get("conditions_all", {}), []
    any_missing, any_unmet = False, False
    for key, rule in conds.items():
        val = inputs.get(key)
        if val is None or val == "UNKNOWN":
            any_missing = True
            reasons.append(f"{key}: 입력 누락 → 판정 불가")
            continue
        op, target = rule["op"], rule["value"]
        ok = {"<=": val <= target, ">=": val >= target, "==": val == target}[op]
        if not ok:
            any_unmet = True
        reasons.append(f"{key} {op} {target}: {'충족' if ok else '미충족'} (현재 {val})")
    if any_unmet:
        return "NOT_FIRED", reasons
    if any_missing:
        return "UNKNOWN", reasons
    return "FIRED", reasons
