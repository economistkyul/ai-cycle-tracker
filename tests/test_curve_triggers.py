"""fetch_curve.evaluate() 트리거 로직 테스트. 네트워크 불필요."""

import sys
from pathlib import Path

# tests/가 패키지(__init__.py 보유)이므로 scripts/를 직접 import 경로에 올린다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from datetime import date, timedelta

import pytest

from fetch_curve import delta_4w, evaluate


def row(days_ago, y2, y10, y30=None, ff_top=3.75, core_cpi=2.9, m3=3.68, usdkrw=1380.0):
    d = (date(2026, 8, 18) - timedelta(days=days_ago)).isoformat()
    y30 = y30 if y30 is not None else y10 + 0.65
    return {
        "date": d, "m3": m3, "y2": y2, "y10": y10, "y30": y30,
        "ff_top": ff_top, "core_cpi": core_cpi, "usdkrw": usdkrw,
        "s210": round(y10 - y2, 4), "s230": round(y30 - y2, 4),
    }


def history(*specs):
    """specs: (days_ago, y2, y10[, y30]) 튜플. 오래된 순으로 정렬해 반환."""
    return sorted([row(*s) for s in specs], key=lambda r: r["date"])


# --- 4주 변화율 ------------------------------------------------------------

def test_delta_4w_none_when_no_old_enough_reference():
    h = history((5, 4.15, 4.60), (0, 4.15, 4.62))
    assert delta_4w(h, len(h) - 1) is None


def test_delta_4w_measures_steepening_as_positive():
    h = history((30, 4.15, 4.45), (0, 4.15, 4.60))
    assert delta_4w(h, len(h) - 1) == pytest.approx(0.15)


def test_delta_4w_ignores_references_older_than_window():
    h = history((90, 4.15, 4.00), (28, 4.15, 4.45), (0, 4.15, 4.60))
    assert delta_4w(h, len(h) - 1) == pytest.approx(0.15)


# --- A: 커브 반전 ----------------------------------------------------------

def test_trigger_a_clear_while_steepening():
    h = history((30, 4.15, 4.45), (0, 4.15, 4.60))
    assert evaluate(h)["triggers"]["A_curve"]["state"] == "clear"


def test_trigger_a_warns_on_single_flattening_reading():
    h = history((31, 4.10, 4.70), (30, 4.10, 4.70), (0, 4.30, 4.60))
    assert evaluate(h)["triggers"]["A_curve"]["state"] == "warn"


def test_trigger_a_fires_on_two_consecutive_flattening_readings():
    h = history((35, 4.00, 4.75), (32, 4.00, 4.75), (2, 4.30, 4.60), (0, 4.35, 4.58))
    assert evaluate(h)["triggers"]["A_curve"]["state"] == "fired"


# --- B: 레벨 (1987년형) ----------------------------------------------------

def test_trigger_b_fires_on_30y_threshold_without_inversion():
    """스티프닝 중이어도 롱엔드 레벨만으로 발화해야 한다 — 1987년형."""
    h = history((30, 4.15, 4.60, 5.40), (0, 4.15, 4.70, 5.80))
    ev = evaluate(h)
    assert ev["triggers"]["A_curve"]["state"] == "clear"
    assert ev["triggers"]["B_level"]["state"] == "fired"
    assert ev["stage"] == 3


def test_trigger_b_fires_on_10y_threshold():
    h = history((30, 4.15, 5.00, 5.20), (0, 4.15, 5.35, 5.55))
    assert evaluate(h)["triggers"]["B_level"]["state"] == "fired"


def test_trigger_b_warns_before_threshold():
    h = history((30, 4.15, 4.60, 5.30), (0, 4.15, 4.65, 5.55))
    assert evaluate(h)["triggers"]["B_level"]["state"] == "warn"


# --- C: 프론트엔드 ---------------------------------------------------------

def test_trigger_c_clear_when_cuts_are_priced():
    h = history((30, 3.50, 4.30), (0, 3.55, 4.40))
    ev = evaluate(h)
    assert ev["triggers"]["C_front"]["state"] == "clear"
    assert ev["stage"] == 1


def test_trigger_c_warns_once_2y_exceeds_policy_top():
    h = history((30, 3.90, 4.50), (0, 3.95, 4.62))
    assert evaluate(h)["triggers"]["C_front"]["state"] == "warn"


def test_trigger_c_fires_at_50bp_gap():
    h = history((30, 4.20, 4.70), (0, 4.30, 4.80))
    assert evaluate(h)["triggers"]["C_front"]["state"] == "fired"


# --- 국면 ------------------------------------------------------------------

def test_current_snapshot_reads_as_late_stage_two():
    """2026-08 실제 좌표: 2Y 4.15 vs 정책상단 3.75 → ②후반."""
    h = history((30, 4.05, 4.50, 5.10), (0, 4.15, 4.60, 5.28))
    ev = evaluate(h)
    assert ev["stage"] == 2
    assert ev["late_stage"] is True
    assert "SOXL" in ev["action"]


def test_stage_three_overrides_action():
    h = history((30, 4.15, 4.60, 5.40), (0, 4.15, 4.70, 5.90))
    assert "매도 시퀀스" in evaluate(h)["action"]


# --- 듀얼 조건 -------------------------------------------------------------

def test_dual_requires_both_conditions():
    h = history((30, 4.15, 4.90), (0, 4.15, 5.05))  # core_cpi 2.9 기본값
    ev = evaluate(h)
    assert ev["triggers"]["dual"]["yield_ok"] is True
    assert ev["triggers"]["dual"]["cpi_ok"] is False
    assert ev["triggers"]["dual"]["fired"] is False


def test_dual_fires_when_both_cross():
    h = [row(30, 4.15, 4.90, core_cpi=3.1), row(0, 4.15, 5.05, core_cpi=3.1)]
    h.sort(key=lambda r: r["date"])
    assert evaluate(h)["triggers"]["dual"]["fired"] is True


def test_alert_flag_set_when_any_hard_trigger_fires():
    h = history((30, 4.15, 4.60, 5.40), (0, 4.15, 4.70, 5.90))
    assert evaluate(h)["alert"] is True


def test_alert_flag_clear_in_quiet_expansion():
    h = history((30, 4.05, 4.50, 5.10), (0, 4.15, 4.60, 5.28))
    assert evaluate(h)["alert"] is False
