import 'dart:math';

import 'package:guess/resources/resources.dart';

import '../utils/similarity_utils.dart';
import 'embedding_service.dart';

class ScoreTraceEvent {
  const ScoreTraceEvent({
    required this.event,
    required this.guess,
    required this.answer,
    required this.finalScore,
    this.semanticRaw,
    this.semanticPercentRaw,
    this.semanticPercentCalibrated,
    this.lexical,
    this.combined,
    this.notes = const [],
  });

  final String event;
  final String guess;
  final String answer;
  final int finalScore;
  final double? semanticRaw;
  final double? semanticPercentRaw;
  final double? semanticPercentCalibrated;
  final int? lexical;
  final int? combined;
  final List<String> notes;
}

class ScoreResult {
  const ScoreResult({required this.score, required this.source});

  final int score;
  final String? source;
}

class CalibrationCurve {
  const CalibrationCurve({required this.x, required this.y});

  final List<double> x;
  final List<double> y;

  factory CalibrationCurve.fromJson(Map<String, dynamic> decoded) {
    final x = (decoded['x_pred'] as List<dynamic>?)
        ?.map((e) => (e as num).toDouble())
        .toList();
    final y = (decoded['y_calibrated'] as List<dynamic>?)
        ?.map((e) => (e as num).toDouble())
        .toList();
    if (x == null || y == null || x.length != y.length || x.length < 2) {
      throw const FormatException('invalid calibration curve');
    }

    final pairs = <MapEntry<double, double>>[];
    for (var i = 0; i < x.length; i += 1) {
      pairs.add(MapEntry(x[i], y[i]));
    }
    pairs.sort((a, b) => a.key.compareTo(b.key));
    return CalibrationCurve(
      x: pairs.map((e) => e.key).toList(growable: false),
      y: pairs.map((e) => e.value).toList(growable: false),
    );
  }

  double apply(double percent) {
    if (x.length != y.length || x.length < 2) {
      return percent;
    }

    if (percent <= x.first) return y.first;
    if (percent >= x.last) return y.last;

    for (var i = 0; i < x.length - 1; i += 1) {
      final left = x[i];
      final right = x[i + 1];
      if (percent < left || percent > right) {
        continue;
      }
      final span = right - left;
      if (span == 0) {
        return y[i];
      }
      final t = (percent - left) / span;
      return y[i] + (y[i + 1] - y[i]) * t;
    }
    return percent;
  }
}

class ManualSimilarityOverrides {
  ManualSimilarityOverrides([Map<String, int>? values])
      : _values = Map<String, int>.from(values ?? const {});

  final Map<String, int> _values;

  factory ManualSimilarityOverrides.fromJson(Object? decoded) {
    if (decoded is! List) {
      return ManualSimilarityOverrides();
    }
    final values = <String, int>{};
    for (final item in decoded) {
      if (item is! Map<String, dynamic>) {
        continue;
      }
      final answer = (item['answer'] as String? ?? '').trim();
      final userInput = (item['user_input'] as String? ?? '').trim();
      final scoreRaw = item['score'];
      if (answer.isEmpty || userInput.isEmpty || scoreRaw is! num) {
        continue;
      }
      values[_pairKey(answer, userInput)] = scoreRaw.round().clamp(0, 95);
    }
    return ManualSimilarityOverrides(values);
  }

  int? score({required String guess, required String answer}) {
    return _values[_pairKey(answer, guess)] ?? _values[_pairKey(guess, answer)];
  }

  static String _pairKey(String a, String b) => '$a\t$b';
}

typedef ScoreTraceCallback = void Function(ScoreTraceEvent event);

class SemanticScorer {
  SemanticScorer({
    required EmbeddingService embeddingService,
    CalibrationCurve? calibration,
    ManualSimilarityOverrides? manualOverrides,
    List<String> semanticAngles = AppStrings.semanticAngles,
    Set<String> functionWords = AppStrings.functionWords,
    ScoreTraceCallback? onTrace,
  })  : _embeddingService = embeddingService,
        _calibration = calibration,
        _manualOverrides = manualOverrides ?? ManualSimilarityOverrides(),
        _semanticAngles = semanticAngles,
        _functionWords = functionWords,
        _onTrace = onTrace;

  final EmbeddingService _embeddingService;
  CalibrationCurve? _calibration;
  ManualSimilarityOverrides _manualOverrides;
  final List<String> _semanticAngles;
  final Set<String> _functionWords;
  final ScoreTraceCallback? _onTrace;
  final Map<String, Map<String, List<double>>> _answerEmbeddingCache = {};

  set calibration(CalibrationCurve? calibration) {
    _calibration = calibration;
  }

  set manualOverrides(ManualSimilarityOverrides manualOverrides) {
    _manualOverrides = manualOverrides;
  }

  void clearAnswerCache() {
    _answerEmbeddingCache.clear();
  }

  Future<void> prefetchAnswer(String answer) async {
    if (answer.isEmpty || _answerEmbeddingCache.containsKey(answer)) {
      return;
    }
    final texts = _semanticAngles.map((angle) => '$angle$answer').toList();
    final results = await _embeddingService.fetchMany(texts);
    if (results == null) {
      return;
    }
    final embeddings = <String, List<double>>{};
    for (final angle in _semanticAngles) {
      final embedding = results['$angle$answer']?.embedding;
      if (embedding == null) {
        return;
      }
      embeddings[angle] = embedding;
    }
    _answerEmbeddingCache[answer] = embeddings;
  }

  Future<ScoreResult> score({
    required String guess,
    required String answer,
  }) async {
    if (guess == answer) {
      _trace(
        event: 'exact_match',
        guess: guess,
        answer: answer,
        finalScore: 100,
        notes: const ['exact_guess'],
      );
      return const ScoreResult(score: 100, source: null);
    }

    if (answer.isNotEmpty) {
      final manual = _manualOverrides.score(guess: guess, answer: answer);
      if (manual != null) {
        final clamped = manual.clamp(0, 95);
        _trace(
          event: 'manual_override',
          guess: guess,
          answer: answer,
          finalScore: clamped,
          notes: const ['manual_override_hit'],
        );
        return ScoreResult(score: clamped, source: null);
      }
    }

    final semantic = await _semanticSimilarityMultiAngle(
      guess: guess,
      answer: answer,
    );
    if (semantic == null) {
      final lexicalFallback = calculateSimilarity(guess, answer);
      final fallbackFinal = normalizeSimilarity(lexicalFallback);
      _trace(
        event: 'fallback_lexical',
        guess: guess,
        answer: answer,
        lexical: lexicalFallback,
        finalScore: fallbackFinal,
        notes: const ['embedding_unavailable_or_null_semantic'],
      );
      return ScoreResult(
          score: fallbackFinal, source: AppStrings.disconnectedSourceLabel);
    }

    final rawPercent = semanticPercent(semantic.cosine).toDouble();
    var percent = _calibration?.apply(rawPercent) ?? rawPercent;
    final lexical = calculateSimilarity(guess, answer);
    final notes = <String>[];

    if (lexical <= 20 && rawPercent < 70) {
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

    if (_containsFunctionWord(guess) && !_containsFunctionWord(answer)) {
      combined = (combined * 0.7).round();
      notes.add('function_word_penalty');
    }

    var finalScore = normalizeSimilarity(combined);
    if (lexical == 0 && rawPercent < 75) {
      finalScore = min(finalScore, 45);
      notes.add('final_cap45_lexical_zero_raw_lt75');
    }
    if (isNearSynonymLike) {
      finalScore = max(finalScore, 30);
      notes.add('near_synonym_floor30');
    }

    _trace(
      event: 'semantic_mix',
      guess: guess,
      answer: answer,
      semanticRaw: semantic.cosine,
      semanticPercentRaw: rawPercent,
      semanticPercentCalibrated: percent,
      lexical: lexical,
      combined: combined,
      finalScore: finalScore,
      notes: notes,
    );
    return ScoreResult(score: finalScore, source: semantic.source);
  }

  Future<_SemanticSimilarity?> _semanticSimilarityMultiAngle({
    required String guess,
    required String answer,
  }) async {
    if (answer.isEmpty) {
      return null;
    }

    final answerEmbeddings = _answerEmbeddingCache[answer];
    final guessTexts = _semanticAngles.map((angle) => '$angle$guess').toList();
    final missingTexts = <String>[
      ...guessTexts,
      if (answerEmbeddings == null)
        ..._semanticAngles.map((angle) => '$angle$answer'),
    ];
    final fetched = await _embeddingService.fetchMany(missingTexts);
    if (fetched == null) {
      return null;
    }

    final scores = <double>[];
    String? source;
    final cachedAnswer = answerEmbeddings ?? <String, List<double>>{};
    final nextAnswerCache = <String, List<double>>{};
    for (final angle in _semanticAngles) {
      final guessEmbedding = fetched['$angle$guess']?.embedding;
      final answerEmbedding =
          cachedAnswer[angle] ?? fetched['$angle$answer']?.embedding;
      if (guessEmbedding == null || answerEmbedding == null) {
        return null;
      }
      source ??=
          fetched['$angle$guess']?.source ?? fetched['$angle$answer']?.source;
      nextAnswerCache[angle] = answerEmbedding;
      scores.add(cosineSimilarity(guessEmbedding, answerEmbedding));
    }

    if (scores.isEmpty) {
      return null;
    }
    if (answerEmbeddings == null) {
      _answerEmbeddingCache[answer] = nextAnswerCache;
    }
    scores.sort();
    final trimmed =
        scores.length >= 3 ? scores.sublist(1, scores.length - 1) : scores;
    final sum = trimmed.fold<double>(0, (acc, v) => acc + v);
    return _SemanticSimilarity(
      cosine: sum / trimmed.length,
      source: source ?? AppStrings.localSourceLabel,
    );
  }

  bool _containsFunctionWord(String text) {
    for (final rune in text.runes) {
      final ch = String.fromCharCode(rune);
      if (_functionWords.contains(ch)) {
        return true;
      }
    }
    return false;
  }

  void _trace({
    required String event,
    required String guess,
    required String answer,
    required int finalScore,
    double? semanticRaw,
    double? semanticPercentRaw,
    double? semanticPercentCalibrated,
    int? lexical,
    int? combined,
    List<String> notes = const [],
  }) {
    _onTrace?.call(
      ScoreTraceEvent(
        event: event,
        guess: guess,
        answer: answer,
        finalScore: finalScore,
        semanticRaw: semanticRaw,
        semanticPercentRaw: semanticPercentRaw,
        semanticPercentCalibrated: semanticPercentCalibrated,
        lexical: lexical,
        combined: combined,
        notes: notes,
      ),
    );
  }
}

class _SemanticSimilarity {
  const _SemanticSimilarity({required this.cosine, required this.source});

  final double cosine;
  final String source;
}
