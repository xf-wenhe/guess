import 'package:flutter_test/flutter_test.dart';
import 'package:guess/services/embedding_service.dart';
import 'package:guess/services/semantic_score_rules.dart';
import 'package:guess/services/semantic_scorer.dart';
import 'package:guess/utils/similarity_utils.dart';

class _NullEmbeddingService extends EmbeddingService {
  _NullEmbeddingService()
      : super(
          localEndpoint: 'http://127.0.0.1:8000/embed',
          onlineEndpoint: '',
          embeddingPrefix: '',
        );

  @override
  Future<Map<String, EmbeddingFetchResult>?> fetchMany(
      List<String> texts) async {
    return null;
  }
}

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

  group('SemanticScoreRules', () {
    const rules = SemanticScoreRules();

    test('applies function word penalty', () {
      final mix = rules.mix(
        semanticPercentRaw: 80,
        semanticPercentCalibrated: 80,
        lexical: 0,
        guessContainsFunctionWord: true,
        answerContainsFunctionWord: false,
      );

      expect(mix.notes, contains('function_word_penalty'));
      expect(mix.finalScore, 45);
    });

    test('caps low-lexical midband calibration', () {
      final mix = rules.mix(
        semanticPercentRaw: 60,
        semanticPercentCalibrated: 90,
        lexical: 0,
        guessContainsFunctionWord: false,
        answerContainsFunctionWord: false,
      );

      expect(mix.semanticPercentCalibrated, 55);
      expect(mix.notes, contains('calibration_midband_cap55_low_lexical'));
      expect(mix.notes, contains('lexical_zero_cap10_unrelated'));
      expect(mix.finalScore, 10);
    });

    test('floors near-synonym-like scores', () {
      final mix = rules.mix(
        semanticPercentRaw: 80,
        semanticPercentCalibrated: 80,
        lexical: 40,
        guessContainsFunctionWord: false,
        answerContainsFunctionWord: false,
      );

      expect(mix.notes, contains('near_synonym_floor30'));
      expect(mix.finalScore, greaterThanOrEqualTo(30));
    });
  });

  group('SemanticScorer fallback', () {
    test('uses lexical fallback when embeddings are unavailable', () async {
      final scorer = SemanticScorer(embeddingService: _NullEmbeddingService());

      final result = await scorer.score(guess: '猫咪', answer: '狗狗');

      expect(
          result.score, normalizeSimilarity(calculateSimilarity('猫咪', '狗狗')));
      expect(result.source, isNotNull);
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
