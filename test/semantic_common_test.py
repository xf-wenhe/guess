import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from semantic_common import apply_calibration, build_calibration  # noqa: E402


class SemanticCommonTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("SEM_CALIBRATION_METHOD", None)

    def test_build_calibration_defaults_to_monotonic_isotonic_curve(self):
        pred = [10, 20, 30, 40, 50, 60]
        target = [10, 80, 20, 70, 60, 90]

        calibration = build_calibration(pred, target)

        self.assertEqual(calibration["method"], "isotonic")
        self.assertEqual(len(calibration["x_pred"]), len(calibration["y_calibrated"]))
        self.assertGreaterEqual(len(calibration["x_pred"]), 2)
        self.assertEqual(calibration["x_pred"], sorted(calibration["x_pred"]))
        self.assertEqual(calibration["y_calibrated"], sorted(calibration["y_calibrated"]))

        calibrated = apply_calibration(
            35,
            calibration["x_pred"],
            calibration["y_calibrated"],
        )
        self.assertGreaterEqual(calibrated, 0)
        self.assertLessEqual(calibrated, 100)

    def test_build_calibration_keeps_legacy_quantile_mean_available(self):
        os.environ["SEM_CALIBRATION_METHOD"] = "legacy"

        calibration = build_calibration([10, 20, 30, 40, 50, 60], [10, 80, 20, 70, 60, 90])

        self.assertEqual(calibration["method"], "quantile_mean")
        self.assertIn("x_pred", calibration)
        self.assertIn("y_calibrated", calibration)


if __name__ == "__main__":
    unittest.main()
