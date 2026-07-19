import unittest, yaml
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.portfolio import risk


def load(name):
    with open(ROOT / "config" / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestConfig(unittest.TestCase):
    def test_parse_all(self):
        for n in ["triggers.yaml", "portfolio.yaml", "sell_sequence.yaml",
                  "regimes.yaml", "moving_average.yaml"]:
            self.assertIsInstance(load(n), dict)

    def test_weight_sums_100(self):
        sums = risk.validate_weights(load("portfolio.yaml"))
        for acc, s in sums.items():
            self.assertAlmostEqual(s, 100, delta=0.5, msg=acc)

    def test_all_sell_buckets_mapped(self):
        pf, seq = load("portfolio.yaml"), load("sell_sequence.yaml")
        mapped = {s["bucket"] for s in seq["sequence"]}
        mapped.add(seq["rule_based_first"]["bucket"])
        mapped.update({"hold", "structural"})   # 명시적 비매도 버킷
        for acc, spec in pf["accounts"].items():
            for bname, b in spec["buckets"].items():
                self.assertIn(b["sell_bucket"], mapped,
                              f"{acc}/{bname}: sell_bucket '{b['sell_bucket']}' 미연결")

    def test_leveraged_required_fields(self):
        pf = load("portfolio.yaml")
        req = ["leverage_multiple", "reset_frequency", "benchmark", "max_weight_pct",
               "max_effective_exposure_pct", "reduction_rule", "exit_rule",
               "reentry_rule", "cooldown_period_days"]
        for t, spec in pf["leveraged_etf_rules"].items():
            for f in req:
                self.assertIn(f, spec, f"{t}.{f} 누락")

    def test_provisional_flags_exist(self):
        tr = load("triggers.yaml")
        self.assertTrue(tr["primary"]["us10y"].get("provisional"))
        self.assertTrue(tr["emergency_override"].get("provisional"))


if __name__ == "__main__":
    unittest.main()
