import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.signals.engine import AxisResult, decide


def axes(**kw):
    base = {"structural_regime": "STRUCTURAL_BULL", "earnings_regime": "BROAD_UPGRADES",
            "valuation_regime": "FAIR", "technical_regime": "TREND_STRONG",
            "macro_financial_stress": "CLEAR", "ai_semiconductor_cycle": "EXPANSION"}
    base.update(kw)
    return {k: AxisResult(k, v) for k, v in base.items()}


class TestEngine(unittest.TestCase):
    def test_risk_on(self):
        self.assertEqual(decide(axes())["final_state"], "RISK_ON")

    def test_principle_b_reduce_leverage(self):
        r = decide(axes(technical_regime="TREND_BREAK"))
        self.assertEqual(r["final_state"], "REDUCE_LEVERAGE")   # 현물 전량매도 아님

    def test_principle_c_fragile(self):
        r = decide(axes(earnings_regime="MULTIPLE_ONLY_RALLY"))
        self.assertEqual(r["final_state"], "HOLD_WITH_HEDGE")

    def test_macro_fired_exits(self):
        r = decide(axes(macro_financial_stress="FIRED"))
        self.assertEqual(r["final_state"], "EXITING")

    def test_missing_critical_unknown(self):
        r = decide(axes(macro_financial_stress="UNKNOWN", earnings_regime="UNKNOWN"))
        self.assertEqual(r["final_state"], "UNKNOWN")   # 원칙 F: CLEAR 반환 금지

    def test_emergency_override_beats_falling_rates(self):
        r = decide(axes(macro_financial_stress="CLEAR"), emergency=True)
        self.assertEqual(r["final_state"], "EXITING")   # 원칙 E

    def test_recommendation_only(self):
        r = decide(axes())
        self.assertTrue(r["recommendation_only"] and r["requires_manual_approval"])


if __name__ == "__main__":
    unittest.main()
