import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from semantic_common import apply_calibration, build_calibration  # noqa: E402
from semantic_common import (  # noqa: E402
    augment_masked_calibration_samples,
    augment_midpoint_calibration_samples,
)


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

    def test_build_calibration_respects_sample_weights_for_isotonic(self):
        pred = [50, 55, 60]
        target = [60, 40, 60]

        unweighted = build_calibration(pred, target)
        weighted = build_calibration(pred, target, [1, 10, 1])

        unweighted_mid = apply_calibration(55, unweighted["x_pred"], unweighted["y_calibrated"])
        weighted_mid = apply_calibration(55, weighted["x_pred"], weighted["y_calibrated"])

        self.assertNotEqual(unweighted_mid, weighted_mid)
        self.assertLess(weighted_mid, unweighted_mid)

    def test_augment_midpoint_calibration_samples_flattens_local_midpoint_jump(self):
        pred = [50, 55, 60]
        target = [50, 50, 80]
        weights = [10, 10, 1]
        midpoint_mask = [True, True, False]

        baseline = build_calibration(pred, target, weights)
        baseline_mid = apply_calibration(56, baseline["x_pred"], baseline["y_calibrated"])

        aug_pred, aug_target, aug_weights = augment_midpoint_calibration_samples(
            pred,
            target,
            weights,
            midpoint_mask,
            radius=3.0,
            steps=2,
            weight_multiplier=0.5,
        )
        augmented = build_calibration(aug_pred, aug_target, aug_weights)
        augmented_mid = apply_calibration(56, augmented["x_pred"], augmented["y_calibrated"])

        self.assertLess(augmented_mid, baseline_mid)
        self.assertGreaterEqual(augmented_mid, 45.0)
        self.assertLessEqual(augmented_mid, 55.0)

    def test_augment_masked_calibration_samples_only_expands_selected_rows(self):
        pred = [20, 40, 60]
        target = [20, 40, 60]
        weights = [1.0, 2.0, 3.0]
        mask = [False, True, False]

        aug_pred, aug_target, aug_weights = augment_masked_calibration_samples(
            pred,
            target,
            weights,
            mask,
            radius=4.0,
            steps=2,
            weight_multiplier=0.25,
        )

        self.assertEqual(aug_pred[:3], pred)
        self.assertEqual(aug_target[:3], target)
        self.assertEqual(aug_weights[:3], weights)
        self.assertEqual(len(aug_pred), len(pred) + 4)
        self.assertEqual(aug_pred[3:], [38.0, 42.0, 36.0, 44.0])
        self.assertEqual(aug_target[3:], [40.0, 40.0, 40.0, 40.0])
        self.assertEqual(aug_weights[3:], [0.5, 0.5, 0.25, 0.25])

    def test_support_positive_augmentation_lifts_supported_band_without_touching_low_zone(self):
        pred = [20, 30, 40, 50, 55, 60, 65, 70]
        target = [10, 20, 30, 60, 40, 40, 80, 90]
        weights = [1.0] * len(pred)
        support_mask = [False, False, False, True, False, False, True, True]

        baseline = build_calibration(pred, target, weights)
        baseline_low = apply_calibration(35, baseline["x_pred"], baseline["y_calibrated"])
        baseline_mid = apply_calibration(56, baseline["x_pred"], baseline["y_calibrated"])

        aug_pred, aug_target, aug_weights = augment_masked_calibration_samples(
            pred,
            target,
            weights,
            support_mask,
            radius=2.0,
            steps=2,
            weight_multiplier=0.15,
        )
        augmented = build_calibration(aug_pred, aug_target, aug_weights)
        augmented_low = apply_calibration(35, augmented["x_pred"], augmented["y_calibrated"])
        augmented_mid = apply_calibration(56, augmented["x_pred"], augmented["y_calibrated"])

        self.assertEqual(augmented_low, baseline_low)
        self.assertGreater(augmented_mid, baseline_mid)
        self.assertGreaterEqual(augmented_mid, 47.0)
        self.assertLessEqual(augmented_mid, 50.0)


if __name__ == "__main__":
    unittest.main()
