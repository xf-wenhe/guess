import 'dart:math';

import '../utils/similarity_utils.dart';

class SemanticScoreMix {
  const SemanticScoreMix({
    required this.finalScore,
    required this.combined,
    required this.semanticPercentCalibrated,
    required this.notes,
  });

  final int finalScore;
  final int combined;
  final double semanticPercentCalibrated;
  final List<String> notes;
}

class SemanticScoreRules {
  const SemanticScoreRules();

  SemanticScoreMix mix({
    required double semanticPercentRaw,
    required double semanticPercentCalibrated,
    required int lexical,
    required bool guessContainsFunctionWord,
    required bool answerContainsFunctionWord,
  }) {
    var percent = semanticPercentCalibrated;
    final notes = <String>[];

    if (lexical <= 20 && semanticPercentRaw < 70) {
      final cappedPercent = min(percent, 55.0);
      if (cappedPercent < percent) {
        percent = cappedPercent;
        notes.add('calibration_midband_cap55_low_lexical');
      }
    }

    var combined = ((percent * 0.8) + (lexical * 0.2)).round();
    final isNearSynonymLike = lexical >= 40 && percent >= 70;

    if (percent < 40) {
      if (percent < 20) {
        combined = min(combined, 10);
        notes.add('semantic_unrelated_cap10');
      }
    } else if (lexical == 0 && percent < 70) {
      combined = min(combined, 10);
      notes.add('lexical_zero_cap10_unrelated');
    }

    if (guessContainsFunctionWord && !answerContainsFunctionWord) {
      combined = (combined * 0.7).round();
      notes.add('function_word_penalty');
    }

    var finalScore = normalizeSimilarity(combined);
    if (lexical == 0 && semanticPercentRaw < 75) {
      finalScore = min(finalScore, 45);
      notes.add('final_cap45_lexical_zero_raw_lt75');
    }
    if (isNearSynonymLike) {
      finalScore = max(finalScore, 30);
      notes.add('near_synonym_floor30');
    }

    return SemanticScoreMix(
      finalScore: finalScore,
      combined: combined,
      semanticPercentCalibrated: percent,
      notes: notes,
    );
  }
}
