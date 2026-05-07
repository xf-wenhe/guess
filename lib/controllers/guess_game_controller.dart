import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:guess/resources/resources.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/guess_models.dart';
import '../services/embedding_service.dart';
import '../services/puzzle_repository.dart';
import '../utils/similarity_utils.dart';

class GuessSubmitOutcome {
  const GuessSubmitOutcome({required this.similarity, required this.isWin});

  final int similarity;
  final bool isWin;
}

class GuessApplyResult {
  const GuessApplyResult({required this.becameWin, required this.becameLose});

  final bool becameWin;
  final bool becameLose;
}

class GuessGameController extends ChangeNotifier {
  GuessGameController({
    required PuzzleRepository puzzleRepository,
    required EmbeddingService embeddingService,
  })  : _puzzleRepository = puzzleRepository,
        _embeddingService = embeddingService;

  static const String onlineEmbeddingKey = 'online_embedding_url';
  static const String localEmbeddingDirKey = 'local_embedding_dir';

  final PuzzleRepository _puzzleRepository;
  final EmbeddingService _embeddingService;

  List<GuessPuzzle> _puzzles = [];
  GuessPuzzle? _current;
  final List<GuessResult> _history = [];
  final Set<String> _usedAnswers = {};

  int _attemptsLeft = 6;
  int _hintIndex = 1;
  bool _won = false;
  bool _lost = false;
  bool _loading = true;
  bool _embeddingUnavailableNotified = false;
  String _embeddingSourceLabel = AppStrings.localSourceLabel;
  String _onlineEmbeddingUrl = '';
  String _localEmbeddingDir = '';
  String _lastGuess = '';
  bool _winBySemantic = false;
  List<double>? _calibrationX;
  List<double>? _calibrationY;
  final Map<String, int> _manualOverrides = {};
  static const List<String> _semanticAngles = AppStrings.semanticAngles;
  static const Set<String> _functionWords = AppStrings.functionWords;
  static const bool _scoreTraceEnabled =
      bool.fromEnvironment('SCORE_TRACE', defaultValue: false);

  List<GuessResult> get history => List.unmodifiable(_history);
  GuessPuzzle? get current => _current;
  int get attemptsLeft => _attemptsLeft;
  int get hintIndex => _hintIndex;
  bool get won => _won;
  bool get lost => _lost;
  bool get loading => _loading;
  bool get hasPuzzles => _puzzles.isNotEmpty;
  String get embeddingSourceLabel => _embeddingSourceLabel;
  String get onlineEmbeddingUrl => _onlineEmbeddingUrl;
  String get localEmbeddingDir => _localEmbeddingDir;
  String get lastGuess => _lastGuess;
  bool get winBySemantic => _winBySemantic;

  bool get categoryUnlocked => _hintIndex >= 2;
  bool get lengthUnlocked => _hintIndex >= 4;
  bool get posUnlocked => _hintIndex >= 5;
  bool get inputDisabled => _won || _lost || _loading;

  Future<void> initialize() async {
    await _loadEmbeddingSettings();
    await _loadSemanticCalibration();
    await _loadManualOverrides();
    await _initGame();
  }

  Future<void> reloadPuzzles() async {
    await _loadPuzzles();
    if (hasPuzzles) {
      _startNewPuzzle();
      notifyListeners();
    }
  }

  void resetGame() {
    _startNewPuzzle();
    notifyListeners();
  }

  bool hasGuessed(String word) {
    return _history.any((h) => h.word == word);
  }

  Future<GuessSubmitOutcome> evaluateGuess(String guess) async {
    final similarity = await _calculateAssociation(guess);
    final isWin = guess == _current?.answer;
    return GuessSubmitOutcome(similarity: similarity, isWin: isWin);
  }

  GuessApplyResult applyGuess(String guess, GuessSubmitOutcome outcome) {
    _history.insert(0, GuessResult(word: guess, match: outcome.similarity));
    _attemptsLeft -= 1;
    if (_current != null && _hintIndex < _current!.hints.length - 1) {
      _hintIndex += 1;
    }

    final becameLose = !outcome.isWin && _attemptsLeft <= 0;
    if (becameLose) {
      _lost = true;
    }

    final becameWin = outcome.isWin;
    if (becameWin) {
      _won = true;
      _winBySemantic = false;
      _lastGuess = guess;
    }

    notifyListeners();
    return GuessApplyResult(becameWin: becameWin, becameLose: becameLose);
  }

  Future<void> updateOnlineEmbeddingUrl(String next) async {
    final prefs = await SharedPreferences.getInstance();
    if (next.isEmpty) {
      await prefs.remove(onlineEmbeddingKey);
    } else {
      await prefs.setString(onlineEmbeddingKey, next);
    }
    _onlineEmbeddingUrl = next;
    _embeddingService.onlineUrl = next;
    _embeddingService.clearCache();
    _embeddingUnavailableNotified = false;
    await refreshEmbeddingSourceLabel();
    notifyListeners();
  }

  Future<void> updateLocalEmbeddingDir(String next) async {
    final prefs = await SharedPreferences.getInstance();
    if (next.isEmpty) {
      await prefs.remove(localEmbeddingDirKey);
    } else {
      await prefs.setString(localEmbeddingDirKey, next);
    }
    _localEmbeddingDir = next;
    notifyListeners();
  }

  Future<void> refreshEmbeddingSourceLabel() async {
    final onlineUrl = _onlineEmbeddingUrl.isNotEmpty
        ? _onlineEmbeddingUrl.trim()
        : _embeddingService.onlineEndpoint.trim();
    if (onlineUrl.isNotEmpty) {
      final onlineOk = await _embeddingService.probe(onlineUrl);
      if (onlineOk) {
        _setEmbeddingSourceLabel(AppStrings.onlineSourceLabel);
        return;
      }
    }

    final localOk =
        await _embeddingService.probe(_embeddingService.localEndpoint);
    _setEmbeddingSourceLabel(
      localOk ? AppStrings.localSourceLabel : AppStrings.disconnectedSourceLabel,
    );
  }

  Future<void> _initGame() async {
    await _loadPuzzles();
    if (hasPuzzles) {
      _startNewPuzzle();
    }
  }

  Future<void> _loadPuzzles() async {
    _loading = true;
    notifyListeners();
    try {
      _puzzles = await _puzzleRepository.loadPuzzles();
      _usedAnswers.clear();
    } catch (err) {
      _puzzles = [];
      debugPrint('Load puzzles failed: $err');
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  void _startNewPuzzle() {
    if (!hasPuzzles) {
      return;
    }
    final base = _pickPuzzle();
    _current = _puzzleRepository.preparePuzzle(base);
    _usedAnswers.add(base.answer);
    _history.clear();
    _attemptsLeft = 6;
    _hintIndex = _current!.hints.isEmpty ? -1 : min(1, _current!.hints.length - 1);
    _won = false;
    _lost = false;
    _winBySemantic = false;
    _lastGuess = '';
  }

  GuessPuzzle _pickPuzzle() {
    final available =
        _puzzles.where((p) => !_usedAnswers.contains(p.answer)).toList();
    if (available.isEmpty) {
      _usedAnswers.clear();
      return _puzzles[Random().nextInt(_puzzles.length)];
    }
    final rand = Random(DateTime.now().millisecondsSinceEpoch);
    return available[rand.nextInt(available.length)];
  }

  Future<int> _calculateAssociation(String guess) async {
    final answer = _current?.answer ?? '';
    if (guess == _current?.answer) {
      _traceScore(
        event: 'exact_match',
        guess: guess,
        answer: answer,
        finalScore: 100,
        notes: const ['exact_guess'],
      );
      return 100;
    }

    if (answer.isNotEmpty) {
      final manual = _manualOverrideScore(guess: guess, answer: answer);
      if (manual != null) {
        final clamped = manual.clamp(0, 95);
        _traceScore(
          event: 'manual_override',
          guess: guess,
          answer: answer,
          finalScore: clamped,
          notes: const ['manual_override_hit'],
        );
        return manual.clamp(0, 95);
      }
    }

    final semantic = await _semanticSimilarityWithHints(guess);
    if (semantic == null || _current == null) {
      final lexicalFallback =
          calculateSimilarity(guess, _current?.answer ?? '');
      final fallbackFinal = normalizeSimilarity(lexicalFallback);
      _traceScore(
        event: 'fallback_lexical',
        guess: guess,
        answer: answer,
        lexical: lexicalFallback,
        finalScore: fallbackFinal,
        notes: const ['embedding_unavailable_or_null_semantic'],
      );
      return fallbackFinal;
    }
    final rawPercent = semanticPercent(semantic).toDouble();
    var percent = _calibrateSemanticPercent(rawPercent);
    final lexical = calculateSimilarity(guess, _current?.answer ?? '');
    final notes = <String>[];

    // Guard against calibration over-lift for weak lexical matches.
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

    if (_containsFunctionWord(guess) &&
        !_containsFunctionWord(_current?.answer ?? '')) {
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
    _traceScore(
      event: 'semantic_mix',
      guess: guess,
      answer: answer,
      semanticRaw: semantic,
      semanticPercentRaw: rawPercent,
      semanticPercentCalibrated: percent,
      lexical: lexical,
      combined: combined,
      finalScore: finalScore,
      notes: notes,
    );
    return finalScore;
  }

  void _traceScore({
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
    if (!_scoreTraceEnabled) {
      return;
    }
    final payload = <String, dynamic>{
      'event': event,
      'guess': guess,
      'answer': answer,
      'semantic_raw_cosine': semanticRaw?.toStringAsFixed(4),
      'semantic_percent_raw': semanticPercentRaw?.toStringAsFixed(2),
      'semantic_percent_calibrated':
        semanticPercentCalibrated?.toStringAsFixed(2),
      'lexical': lexical,
      'combined': combined,
      'final': finalScore,
      'notes': notes,
    };
    debugPrint('[score_trace] ${jsonEncode(payload)}');
  }

  Future<double?> _semanticSimilarityWithHints(String guess) async {
    return _semanticSimilarityMultiAngle(guess);
  }

  Future<double?> _semanticSimilarityMultiAngle(String guess) async {
    final answer = _current?.answer;
    if (answer == null) {
      return null;
    }
    final scores = <double>[];
    for (final angle in _semanticAngles) {
      final guessEmbedding = await _fetchEmbedding('$angle$guess');
      if (guessEmbedding == null) {
        return null;
      }
      final answerEmbedding = await _fetchEmbedding('$angle$answer');
      if (answerEmbedding == null) {
        return null;
      }
      scores.add(cosineSimilarity(guessEmbedding, answerEmbedding));
    }
    if (scores.isEmpty) {
      return null;
    }
    scores.sort();
    final trimmed =
        scores.length >= 3 ? scores.sublist(1, scores.length - 1) : scores;
    final sum = trimmed.fold<double>(0, (acc, v) => acc + v);
    return sum / trimmed.length;
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

  Future<void> _loadSemanticCalibration() async {
    try {
      String raw;
      try {
        raw = '';
        for (final path in AppAssets.semanticCalibrationCandidates) {
          try {
            raw = await rootBundle.loadString(path);
            break;
          } catch (_) {
            continue;
          }
        }
        if (raw.isEmpty) {
          _calibrationX = null;
          _calibrationY = null;
          return;
        }
      } catch (_) {
        _calibrationX = null;
        _calibrationY = null;
        return;
      }
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      final x = (decoded['x_pred'] as List<dynamic>?)
          ?.map((e) => (e as num).toDouble())
          .toList();
      final y = (decoded['y_calibrated'] as List<dynamic>?)
          ?.map((e) => (e as num).toDouble())
          .toList();
      if (x == null || y == null || x.length != y.length || x.length < 2) {
        _calibrationX = null;
        _calibrationY = null;
        return;
      }

      final pairs = <MapEntry<double, double>>[];
      for (var i = 0; i < x.length; i += 1) {
        pairs.add(MapEntry(x[i], y[i]));
      }
      pairs.sort((a, b) => a.key.compareTo(b.key));

      _calibrationX = pairs.map((e) => e.key).toList();
      _calibrationY = pairs.map((e) => e.value).toList();
    } catch (_) {
      _calibrationX = null;
      _calibrationY = null;
    }
  }

  Future<void> _loadManualOverrides() async {
    _manualOverrides.clear();
    try {
        final raw =
          await rootBundle.loadString(AppAssets.manualSimilarityOverrides);
      final decoded = jsonDecode(raw);
      if (decoded is! List) {
        return;
      }
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
        final score = scoreRaw.round().clamp(0, 95);
        _manualOverrides[_pairKey(answer, userInput)] = score;
      }
    } catch (_) {
      _manualOverrides.clear();
    }
  }

  int? _manualOverrideScore({required String guess, required String answer}) {
    return _manualOverrides[_pairKey(answer, guess)] ??
        _manualOverrides[_pairKey(guess, answer)];
  }

  String _pairKey(String a, String b) => '$a\t$b';

  double _calibrateSemanticPercent(double percent) {
    final x = _calibrationX;
    final y = _calibrationY;
    if (x == null || y == null || x.length != y.length || x.length < 2) {
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

  Future<List<double>?> _fetchEmbedding(String text) async {
    final result = await _embeddingService.fetch(text);
    if (result == null) {
      _notifyEmbeddingUnavailable();
      return null;
    }
    _setEmbeddingSourceLabel(result.source);
    return result.embedding;
  }

  void _notifyEmbeddingUnavailable() {
    if (_embeddingUnavailableNotified) {
      return;
    }
    _embeddingUnavailableNotified = true;
    _setEmbeddingSourceLabel(AppStrings.disconnectedSourceLabel);
  }

  void _setEmbeddingSourceLabel(String label) {
    if (_embeddingSourceLabel == label) {
      return;
    }
    _embeddingSourceLabel = label;
    notifyListeners();
  }

  Future<void> _loadEmbeddingSettings() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(onlineEmbeddingKey);
    final savedLocal = prefs.getString(localEmbeddingDirKey);
    final fallback = _embeddingService.onlineEndpoint.trim();
    final next = (saved ?? fallback).trim();
    _onlineEmbeddingUrl = next;
    _localEmbeddingDir = (savedLocal ?? '').trim();
    _embeddingService.onlineUrl = next;
    await refreshEmbeddingSourceLabel();
    notifyListeners();
  }
}
