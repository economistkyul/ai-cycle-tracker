import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.portfolio import risk


class TestRisk(unittest.TestCase):
    def setUp(self):
        self.pf = risk.load_portfolio()
        self.vals = {"account_a": 1000, "account_b": 100}

    def test_effective_exceeds_nominal(self):
        exp = risk.combined_exposure(self.pf, self.vals)
        self.assertGreater(exp["effective_exposure_pct"], 100)   # 3x 21% → 명목 초과

    def test_overlap_detected(self):
        exp = risk.combined_exposure(self.pf, self.vals)
        for h in ["엔비디아", "브로드컴", "마이크론", "TQQQ"]:
            self.assertIn(h, exp["overlap_holdings"])            # 계좌 간 중복 합산

    def test_weight_sum_validation_raises(self):
        bad = {"accounts": {"x": {"buckets": {"a": {"weight_pct": 50}}}}}
        with self.assertRaises(ValueError):
            risk.validate_weights(bad)

    def test_stress_scales_with_beta(self):
        exp = risk.combined_exposure(self.pf, self.vals)
        sl = risk.stress_loss(exp)
        self.assertLess(sl["20d"], sl["1d"])   # 더 큰 쇼크 = 더 큰 손실(음수)


if __name__ == "__main__":
    unittest.main()
