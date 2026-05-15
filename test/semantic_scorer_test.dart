import 'package:flutter_test/flutter_test.dart';
import 'package:guess/services/semantic_scorer.dart';
import 'package:guess/utils/similarity_utils.dart';

void main() {
  group('CalibrationCurve', () {
    test('sorts points and interpolates linearly', () {
      final curve = CalibrationCurve.fromJson({
        'x_pred': [100, 0, 50],
        'y_calibrated': [90, 10, 40],
      });

      expect(curve.apply(-1), 10);
      expect(curve.apply(25), 25);
      expect(curve.apply(75), 65);
      expect(curve.apply(101), 90);
    });

    test('rejects malformed curves', () {
      expect(
        () => CalibrationCurve.fromJson({
          'x_pred': [0],
          'y_calibrated': [0],
        }),
        throwsFormatException,
      );
    });
  });

  group('ManualSimilarityOverrides', () {
    test('loads bidirectional clamped manual scores', () {
      final overrides = ManualSimilarityOverrides.fromJson([
        {'answer': '猫咪', 'user_input': '小猫', 'score': 120},
      ]);

      expect(overrides.score(guess: '小猫', answer: '猫咪'), 95);
      expect(overrides.score(guess: '猫咪', answer: '小猫'), 95);
      expect(overrides.score(guess: '狗狗', answer: '猫咪'), isNull);
    });
  });

  group('similarity utils', () {
    test('keeps exact lexical match at 100 before final answer normalization',
        () {
      expect(calculateSimilarity('太阳', '太阳'), 100);
      expect(normalizeSimilarity(100), 95);
      expect(semanticPercent(0.876), 88);
    });
  });
}
