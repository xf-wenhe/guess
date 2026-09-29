import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from semantic_common import (  # noqa: E402
    apply_calibration,
    apply_global_calibration,
    apply_relation_calibration,
    build_calibration,
    constrain_calibration_interval,
)
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

    def test_midpoint_calibration_margin_covers_raw_56_edge(self):
        pred = [53.5, 58.5]
        target = [50, 80]
        weights = [10.0, 1.0]
        midpoint_mask = [True, False]

        baseline_pred, baseline_target, baseline_weights = augment_midpoint_calibration_samples(
            pred,
            target,
            weights,
            midpoint_mask,
            radius=2.5,
            steps=2,
            weight_multiplier=0.5,
        )
        baseline = build_calibration(baseline_pred, baseline_target, baseline_weights)
        baseline_edge = apply_calibration(56.93, baseline["x_pred"], baseline["y_calibrated"])

        margin_pred, margin_target, margin_weights = augment_midpoint_calibration_samples(
            pred,
            target,
            weights,
            midpoint_mask,
            radius=3.5,
            steps=2,
            weight_multiplier=0.5,
        )
        margin = build_calibration(margin_pred, margin_target, margin_weights)
        margin_edge = apply_calibration(56.93, margin["x_pred"], margin["y_calibrated"])

        self.assertGreater(baseline_edge, 55.0)
        self.assertLessEqual(margin_edge, 55.0)

    def test_constrain_calibration_interval_caps_midpoint_neighborhood(self):
        calibration = build_calibration(
            [40.0, 50.0, 55.0, 57.0, 60.0, 80.0],
            [30.0, 45.0, 60.0, 70.0, 80.0, 90.0],
        )

        constrained = constrain_calibration_interval(
            calibration,
            lower=50.0,
            upper=58.0,
            target_low=45.0,
            target_high=55.0,
        )

        self.assertEqual(constrained["x_pred"], sorted(constrained["x_pred"]))
        self.assertEqual(
            constrained["y_calibrated"],
            sorted(constrained["y_calibrated"]),
        )
        for score in (50.0, 55.0, 57.0, 58.0):
            calibrated = apply_calibration(
                score,
                constrained["x_pred"],
                constrained["y_calibrated"],
            )
            self.assertGreaterEqual(calibrated, 45.0)
            self.assertLessEqual(calibrated, 55.0)
        self.assertGreater(
            apply_calibration(60.0, constrained["x_pred"], constrained["y_calibrated"]),
            55.0,
        )

    def test_relation_calibration_does_not_remap_unrelated_rows(self):
        calibration = {
            "x_pred": [0.0, 50.0, 100.0],
            "y_calibrated": [0.0, 70.0, 100.0],
            "relation_calibrations": {
                "antonym_mid": {
                    "x_pred": [0.0, 100.0],
                    "y_calibrated": [0.0, 100.0],
                    "target_low": 45.0,
                    "target_high": 55.0,
                }
            },
        }

        self.assertEqual(apply_relation_calibration(50.0, calibration), 70.0)
        self.assertEqual(apply_relation_calibration(50.0, calibration, "antonym_mid"), 50.0)
        self.assertEqual(apply_relation_calibration(90.0, calibration, "antonym_mid"), 55.0)

    def test_global_calibration_ignores_relation_specific_profiles(self):
        calibration = {
            "x_pred": [0.0, 100.0],
            "y_calibrated": [0.0, 100.0],
            "relation_calibrations": {
                "antonym_mid": {
                    "x_pred": [0.0, 100.0],
                    "y_calibrated": [0.0, 100.0],
                    "target_low": 45.0,
                    "target_high": 55.0,
                }
            },
        }

        self.assertAlmostEqual(apply_global_calibration(60.87, calibration), 60.87)
        self.assertEqual(
            apply_relation_calibration(60.87, calibration, "antonym_mid"),
            55.0,
        )

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
