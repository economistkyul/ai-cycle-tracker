import unittest
from datetime import date
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.signals.macro import eval_threshold_signal, eval_macro, eval_emergency_override

CFG = {"name": "10Y", "fire_threshold": 5.0, "severity_threshold": 5.3,
       "clear_threshold": 4.7, "confirm_obs": 3, "clear_confirm_obs": 2,
       "armed_proximity": 0.95, "stale_after_days": 10}
TODAY = date(2026, 7, 17)


def hist(vals, metric="us10y", start_day=10):
    return [{"as_of": f"2026-07-{start_day+i:02d}",
             "metrics": {metric: {"value": v, "observation_date": f"2026-07-{start_day+i:02d}",
                                  "stale_after_days": 10}}} for i, v in enumerate(vals)]


class TestMacro(unittest.TestCase):
    def test_boundary_no_fire_below(self):
        r = eval_threshold_signal(hist([4.99, 4.99, 4.99]), "us10y", CFG, TODAY)
        self.assertEqual(r.state, "ARMED")   # 근접이지만 미발화

    def test_fire_needs_consecutive(self):
        r = eval_threshold_signal(hist([5.1, 4.9, 5.1]), "us10y", CFG, TODAY)
        self.assertNotEqual(r.state, "FIRED")   # 연속 3회 미충족
        r = eval_threshold_signal(hist([5.0, 5.0, 5.0]), "us10y", CFG, TODAY)
        self.assertEqual(r.state, "FIRED")

    def test_hysteresis_keeps_fired(self):
        r = eval_threshold_signal(hist([4.9, 4.9]), "us10y", CFG, TODAY, prev_state="FIRED")
        self.assertEqual(r.state, "FIRED")   # 4.7 이하 2회 확인 전까지 유지
        r = eval_threshold_signal(hist([4.6, 4.65]), "us10y", CFG, TODAY, prev_state="FIRED")
        self.assertEqual(r.state, "CLEAR")

    def test_stale_returns_unknown(self):
        h = [{"as_of": "2026-06-01", "metrics": {"us10y": {
            "value": 5.5, "observation_date": "2026-06-01", "stale_after_days": 10}}}]
        r = eval_threshold_signal(h, "us10y", CFG, TODAY)
        self.assertEqual(r.state, "UNKNOWN")   # 원칙 F: 노후 데이터로 FIRED 금지

    def test_dual_condition(self):
        cpi_cfg = dict(CFG, fire_threshold=3.0, clear_threshold=2.8, confirm_obs=2)
        triggers = {"primary": {"us10y": CFG, "core_cpi": cpi_cfg},
                    "dual_condition_required": True, "rate_velocity": {}}
        h = hist([5.1, 5.1, 5.1]) 
        for s, extra in zip(h, [2.5, 2.5, 2.5]):
            s["metrics"]["core_cpi"] = {"value": extra, "observation_date": s["as_of"],
                                        "stale_after_days": 45}
        r = eval_macro(h, triggers, TODAY)
        self.assertEqual(r["state"], "ARMED")   # 10Y만 FIRED → 전체 FIRED 아님

    def test_emergency_override(self):
        cfg = {"conditions_all": {
            "forward_eps_3m_change_pct": {"op": "<=", "value": -5.0},
            "hy_spread_widening_bp_20d": {"op": ">=", "value": 150},
            "technical_regime": {"op": "==", "value": "TREND_BREAK"}}}
        state, _ = eval_emergency_override({"forward_eps_3m_change_pct": -8,
                                            "hy_spread_widening_bp_20d": 200,
                                            "technical_regime": "TREND_BREAK"}, cfg)
        self.assertEqual(state, "FIRED")
        state, _ = eval_emergency_override({"forward_eps_3m_change_pct": -8}, cfg)
        self.assertEqual(state, "UNKNOWN")   # v3: 누락은 미충족(NOT_FIRED)이 아니라 UNKNOWN


if __name__ == "__main__":
    unittest.main()
