import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:guess/resources/resources.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/guess_models.dart';
import '../services/embedding_service.dart';
import '../services/puzzle_repository.dart';
import '../services/semantic_scorer.dart';

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
        _embeddingService = embeddingService {
    _semanticScorer = SemanticScorer(
      embeddingService: _embeddingService,
      onTrace: _traceScore,
    );
  }

  static const String onlineEmbeddingKey = 'online_embedding_url';
  static const String localEmbeddingDirKey = 'local_embedding_dir';

  final PuzzleRepository _puzzleRepository;
  final EmbeddingService _embeddingService;
  late final SemanticScorer _semanticScorer;

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
      localOk
          ? AppStrings.localSourceLabel
          : AppStrings.disconnectedSourceLabel,
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
    _hintIndex =
        _current!.hints.isEmpty ? -1 : min(1, _current!.hints.length - 1);
    _won = false;
    _lost = false;
    _winBySemantic = false;
    _lastGuess = '';
    _semanticScorer.clearAnswerCache();
    unawaited(_semanticScorer.prefetchAnswer(_current!.answer));
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
    final result = await _semanticScorer.score(guess: guess, answer: answer);
    if (result.source == AppStrings.disconnectedSourceLabel) {
      _notifyEmbeddingUnavailable();
    } else if (result.source != null) {
      _setEmbeddingSourceLabel(result.source!);
    }
    return result.score;
  }

  void _traceScore(ScoreTraceEvent event) {
    if (!_scoreTraceEnabled) {
      return;
    }
    final payload = <String, dynamic>{
      'event': event.event,
      'guess': event.guess,
      'answer': event.answer,
      'semantic_raw_cosine': event.semanticRaw?.toStringAsFixed(4),
      'semantic_percent_raw': event.semanticPercentRaw?.toStringAsFixed(2),
      'semantic_percent_calibrated':
          event.semanticPercentCalibrated?.toStringAsFixed(2),
      'lexical': event.lexical,
      'combined': event.combined,
      'final': event.finalScore,
      'notes': event.notes,
    };
    debugPrint('[score_trace] ${jsonEncode(payload)}');
  }

  Future<void> _loadSemanticCalibration() async {
    try {
      var raw = '';
      for (final path in AppAssets.semanticCalibrationCandidates) {
        try {
          raw = await rootBundle.loadString(path);
          break;
        } catch (_) {
          continue;
        }
      }
      if (raw.isEmpty) {
        _semanticScorer.calibration = null;
        return;
      }
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      _semanticScorer.calibration = CalibrationCurve.fromJson(decoded);
    } catch (_) {
      _semanticScorer.calibration = null;
    }
  }

  Future<void> _loadManualOverrides() async {
    try {
      final raw =
          await rootBundle.loadString(AppAssets.manualSimilarityOverrides);
      _semanticScorer.manualOverrides =
          ManualSimilarityOverrides.fromJson(jsonDecode(raw));
    } catch (_) {
      _semanticScorer.manualOverrides = ManualSimilarityOverrides();
    }
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
    unawaited(refreshEmbeddingSourceLabel());
    notifyListeners();
  }

  void _notifyEmbeddingUnavailable() {
    if (_embeddingUnavailableNotified) {
      return;
    }
    _embeddingUnavailableNotified = true;
    _setEmbeddingSourceLabel(AppStrings.disconnectedSourceLabel);
  }

  void _setEmbeddingSourceLabel(String label) {
    if (label != AppStrings.disconnectedSourceLabel) {
      _embeddingUnavailableNotified = false;
    }
    if (_embeddingSourceLabel == label) {
      return;
    }
    _embeddingSourceLabel = label;
    notifyListeners();
  }
}
