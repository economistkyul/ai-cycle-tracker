"""v3 수정 검증 — 작성 시점에는 실패해야 하는 테스트."""
import unittest, yaml
from datetime import date
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TODAY = date(2026, 7, 17)


def snap(as_of, metric, value, obs_date, release_date=None, stale=45):
    return {"as_of": as_of, "metrics": {metric: {
        "value": value, "observation_date": obs_date,
        "release_date": release_date or obs_date, "stale_after_days": stale}}}


class T1_CpiDedup(unittest.TestCase):
    """동일 CPI 발표값이 주간 스냅샷 2개에 복사돼도 1회로만 계산 → FIRED 금지."""
    def test_same_release_counted_once(self):
        from src.signals.macro import eval_threshold_signal
        cfg = {"name": "CPI", "fire_threshold": 3.0, "clear_threshold": 2.8,
               "confirm_obs": 2, "clear_confirm_obs": 1, "confirm_unit": "release",
               "armed_proximity": 0.95, "stale_after_days": 45}
        h = [snap("2026-07-11", "core_cpi", 3.1, "2026-06-30", "2026-07-10"),
             snap("2026-07-17", "core_cpi", 3.1, "2026-06-30", "2026-07-10")]  # 같은 발표 복사
        r = eval_threshold_signal(h, "core_cpi", cfg, TODAY)
        self.assertNotEqual(r.state, "FIRED")   # 고유 release 1건뿐


class T2_HysteresisPersistence(unittest.TestCase):
    """상태 저장소 경유 — 이전 실행 FIRED가 다음 실행 4.9에서도 유지."""
    def test_state_store_roundtrip(self):
        from src.core.state_store import load_states, save_states
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "signal_state.yaml"
            save_states({"us10y": {"state": "FIRED", "entered_at": "2026-07-10",
                                   "reason": "테스트"}}, f)
            st = load_states(f)
            self.assertEqual(st["us10y"]["state"], "FIRED")

    def test_fired_persists_at_49(self):
        from src.signals.macro import eval_threshold_signal
        cfg = {"name": "10Y", "fire_threshold": 5.0, "clear_threshold": 4.7,
               "confirm_obs": 3, "clear_confirm_obs": 2, "confirm_unit": "trading_day",
               "armed_proximity": 0.95, "stale_after_days": 10}
        h = [snap("2026-07-16", "us10y", 4.9, "2026-07-15", stale=10),
             snap("2026-07-17", "us10y", 4.9, "2026-07-16", stale=10)]
        r = eval_threshold_signal(h, "us10y", cfg, TODAY, prev_state="FIRED")
        self.assertEqual(r.state, "FIRED")


class T3_StructuralNotBull(unittest.TestCase):
    """weakening + selling → 강세 반환 금지."""
    def test_weakening_selling_is_bear(self):
        from src.signals.structural import eval_structural
        obs = {"usdkrw_trend": "weakening", "foreign_net_flow": "selling",
               "oil_trend": "rising"}
        r = eval_structural(obs, min_inputs=3)
        self.assertNotIn(r["state"], ("STRUCTURAL_BULL", "BULL_WITH_LATE_CYCLE_RISK"))
        self.assertEqual(r["state"], "STRUCTURAL_BEAR")


class T4_FutureDates(unittest.TestCase):
    """미래 관측일/발표일 → fresh 금지, 사용 금지."""
    def test_future_obs_not_fresh(self):
        from src.core.observations import is_fresh
        self.assertFalse(is_fresh({"observation_date": "2026-08-01",
                                   "stale_after_days": 10}, TODAY))

    def test_unreleased_excluded(self):
        from src.core.observations import confirm_series
        h = [snap("2026-07-17", "core_cpi", 3.5, "2026-06-30", "2026-08-10")]  # 미발표
        s = confirm_series(h, "core_cpi", "release", TODAY)
        self.assertEqual(len(s), 0)


class T5_EmergencyTriState(unittest.TestCase):
    """입력 누락 → NOT_FIRED가 아니라 UNKNOWN."""
    def test_missing_is_unknown(self):
        from src.signals.macro import eval_emergency_override
        cfg = {"conditions_all": {
            "forward_eps_3m_change_pct": {"op": "<=", "value": -5.0},
            "hy_spread_widening_bp_20d": {"op": ">=", "value": 150},
            "technical_regime": {"op": "==", "value": "TREND_BREAK"}}}
        state, _ = eval_emergency_override({"forward_eps_3m_change_pct": -8}, cfg)
        self.assertEqual(state, "UNKNOWN")

    def test_all_met_fired(self):
        from src.signals.macro import eval_emergency_override
        cfg = {"conditions_all": {
            "forward_eps_3m_change_pct": {"op": "<=", "value": -5.0}}}
        state, _ = eval_emergency_override({"forward_eps_3m_change_pct": -8}, cfg)
        self.assertEqual(state, "FIRED")


class T6_SellPlanner(unittest.TestCase):
    def test_exiting_activates_sequence(self):
        from src.execution.planner import build_plan
        with open(ROOT / "config" / "sell_sequence.yaml", encoding="utf-8") as f:
            seq = yaml.safe_load(f)
        plan = build_plan("EXITING", {"macro_financial_stress": "FIRED"}, seq)
        self.assertTrue(plan["recommendation_only"])
        active = [s for s in plan["steps"] if s["active"]]
        self.assertGreaterEqual(len(active), 4)
        rb = next(s for s in plan["steps"] if s["bucket"] == "rule_based")
        self.assertEqual(rb["target_reduction_pct"], 100)

    def test_risk_on_nothing_active(self):
        from src.execution.planner import build_plan
        with open(ROOT / "config" / "sell_sequence.yaml", encoding="utf-8") as f:
            seq = yaml.safe_load(f)
        plan = build_plan("RISK_ON", {}, seq)
        self.assertEqual([s for s in plan["steps"] if s["active"]
                          and s["bucket"] != "rule_based"], [])


class T7_DemoDataWarning(unittest.TestCase):
    def test_example_values_flagged_demo(self):
        from src.portfolio import risk
        vals, is_demo = risk.load_account_values()
        if vals and "example" in str(risk.account_values_source()):
            self.assertTrue(is_demo)


class T8_TechnicalBoundary(unittest.TestCase):
    def _cfg(self):
        return {"windows": {"short": 20, "mid": 50, "long": 200},
                "hysteresis_pct": 1.0, "extended_disparity_pct": 10.0,
                "pullback_floor_pct": -3.0,
                "confirm_days": {"bull_regime": {"break_confirm": 3, "reentry_confirm": 5},
                                 "bear_regime": {"break_confirm": 1, "reentry_confirm": 10}}}

    def test_break_after_confirm(self):
        from src.signals.technical import eval_technical
        closes = [100.0] * 60 + [95.0, 95.0, 95.0]   # 50MA 확실히 하회 3일
        r = eval_technical(closes, self._cfg(), break_confirm=3, reentry_confirm=5)
        self.assertEqual(r["state"], "TREND_BREAK")

    def test_two_days_only_warning(self):
        from src.signals.technical import eval_technical
        closes = [100.0] * 61 + [95.0, 95.0]
        r = eval_technical(closes, self._cfg(), break_confirm=3, reentry_confirm=5)
        self.assertEqual(r["state"], "TREND_WARNING")

    def test_drawdown_reported(self):
        from src.signals.technical import eval_technical
        closes = [100.0] * 60 + [95.0, 95.0, 95.0]
        r = eval_technical(closes, self._cfg(), break_confirm=3, reentry_confirm=5)
        self.assertIn("drawdown_from_high_pct", r)


class T9_PerAssetLeverageAction(unittest.TestCase):
    def test_tqqq_warning_maps_reduction(self):
        from src.signals.technical import leveraged_action
        rules = {"TQQQ": {"reduction_rule": "50% 축소", "exit_rule": "전량",
                          "reentry_rule": "5일 확인", "cooldown_period_days": 10}}
        act = leveraged_action("TQQQ", "TREND_WARNING", rules)
        self.assertIn("50%", act["action"])
        act = leveraged_action("TQQQ", "TREND_BREAK", rules)
        self.assertIn("전량", act["action"])


class T10_KrwStageAuto(unittest.TestCase):
    def test_stage3_derived(self):
        from src.signals.structural import derive_krw_stage
        stage, warn = derive_krw_stage({"usdkrw_trend": "weakening",
                                        "foreign_net_flow": "selling"})
        self.assertEqual(stage, 3)

    def test_manual_conflict_warns(self):
        from src.signals.structural import derive_krw_stage
        stage, warn = derive_krw_stage({"usdkrw_trend": "weakening",
                                        "foreign_net_flow": "selling"}, manual_stage=1)
        self.assertEqual(stage, 3)          # 유도값 우선
        self.assertTrue(warn)               # 모순 경고


if __name__ == "__main__":
    unittest.main()
