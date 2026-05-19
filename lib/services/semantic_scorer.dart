import 'package:guess/resources/resources.dart';

import '../utils/similarity_utils.dart';
import 'embedding_service.dart';
import 'scoring_models.dart';
import 'semantic_score_rules.dart';

export 'scoring_models.dart';

typedef ScoreTraceCallback = void Function(ScoreTraceEvent event);

class SemanticScorer {
  SemanticScorer({
    required EmbeddingService embeddingService,
    CalibrationCurve? calibration,
    ManualSimilarityOverrides? manualOverrides,
    List<String> semanticAngles = AppStrings.semanticAngles,
    Set<String> functionWords = AppStrings.functionWords,
    SemanticScoreRules scoreRules = const SemanticScoreRules(),
    ScoreTraceCallback? onTrace,
  })  : _embeddingService = embeddingService,
        _calibration = calibration,
        _manualOverrides = manualOverrides ?? ManualSimilarityOverrides(),
        _semanticAngles = semanticAngles,
        _functionWords = functionWords,
        _scoreRules = scoreRules,
        _onTrace = onTrace;

  final EmbeddingService _embeddingService;
  CalibrationCurve? _calibration;
  ManualSimilarityOverrides _manualOverrides;
  final List<String> _semanticAngles;
  final Set<String> _functionWords;
  final SemanticScoreRules _scoreRules;
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
    final percent = _calibration?.apply(rawPercent) ?? rawPercent;
    final lexical = calculateSimilarity(guess, answer);
    final mix = _scoreRules.mix(
      semanticPercentRaw: rawPercent,
      semanticPercentCalibrated: percent,
      lexical: lexical,
      guessContainsFunctionWord: _containsFunctionWord(guess),
      answerContainsFunctionWord: _containsFunctionWord(answer),
    );

    _trace(
      event: 'semantic_mix',
      guess: guess,
      answer: answer,
      semanticRaw: semantic.cosine,
      semanticPercentRaw: rawPercent,
      semanticPercentCalibrated: mix.semanticPercentCalibrated,
      lexical: lexical,
      combined: mix.combined,
      finalScore: mix.finalScore,
      notes: mix.notes,
    );
    return ScoreResult(score: mix.finalScore, source: semantic.source);
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
