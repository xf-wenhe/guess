import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:guess/config/server_config.dart';
import 'package:guess/controllers/account_controller.dart';
import 'package:guess/resources/resources.dart';
import 'package:guess/services/connection_service.dart';
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
    required ConnectionService connectionService,
    required AccountController accountController,
  })  : _puzzleRepository = puzzleRepository,
        _embeddingService = embeddingService,
        _connectionService = connectionService,
        _accountController = accountController {
    _semanticScorer = SemanticScorer(
      embeddingService: _embeddingService,
      onTrace: _traceScore,
    );
  }

  static const String onlineEmbeddingKey = 'online_embedding_url';
  static const String localEmbeddingDirKey = 'local_embedding_dir';
  static const String puzzlePathKey = 'puzzle_path';

  final PuzzleRepository _puzzleRepository;
  final EmbeddingService _embeddingService;
  final ConnectionService _connectionService;
  final AccountController _accountController;
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
  String _puzzlePath = '';
  String _lastGuess = '';
  bool _winBySemantic = false;
  String? _puzzleLoadError;
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
  String get puzzlePath => _puzzlePath;
  String get lastGuess => _lastGuess;
  bool get winBySemantic => _winBySemantic;
  String? get puzzleLoadError => _puzzleLoadError;
  int get bestMatch => _bestMatch;
  int _bestMatch = 0;

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
    // 重新探测端点，按优先级顺序重试
    await _refreshConnectionStatus();
    await _loadPuzzles();
    if (hasPuzzles) {
      _startNewPuzzle();
      notifyListeners();
    }
  }

  /// 启用服务器词库模式并重新加载
  Future<void> enableServerPuzzlesAndReload() async {
    _puzzleRepository.enableServerPuzzles();
    // 设置词库端点
    if (_connectionService.connectedPuzzleEndpoint != null) {
      _puzzleRepository.setActiveEndpoint(_connectionService.connectedPuzzleEndpoint!);
    }
    await reloadPuzzles();
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
    // 更新 bestMatch 缓存
    if (outcome.similarity > _bestMatch) {
      _bestMatch = outcome.similarity;
    }
    _attemptsLeft -= 1;
    if (_current != null && _hintIndex < _current!.hints.length - 1) {
      _hintIndex += 1;
    }

    final becameLose = !outcome.isWin && _attemptsLeft <= 0;
    if (becameLose) {
      _lost = true;
      _recordGameResult(false);
    }

    final becameWin = outcome.isWin;
    if (becameWin) {
      _won = true;
      _winBySemantic = false;
      _lastGuess = guess;
      _recordGameResult(true, _hintIndex);
    }

    notifyListeners();
    return GuessApplyResult(becameWin: becameWin, becameLose: becameLose);
  }

  /// 记录答题结果到服务器
  void _recordGameResult(bool correct, [int hintIndex = -1]) {
    if (_accountController.puzzleMode == PuzzleMode.server) {
      _accountController.recordGameResult(correct: correct, hintIndex: hintIndex);
    }
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

  Future<void> updatePuzzlePath(String next) async {
    final prefs = await SharedPreferences.getInstance();
    if (next.isEmpty) {
      await prefs.remove(puzzlePathKey);
    } else {
      await prefs.setString(puzzlePathKey, next);
    }
    _puzzlePath = next;
    _puzzleRepository.setLocalPuzzlePath(next);
    _puzzleLoadError = null;
    await reloadPuzzles();
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
      _puzzleLoadError = null;
    } on PuzzleLoadException catch (err) {
      _puzzles = [];
      _puzzleLoadError = err.message;
      ConnectionLog.error('Game', '加载词库失败', err);
    } catch (err) {
      _puzzles = [];
      _puzzleLoadError = '加载词库失败: $err';
      ConnectionLog.error('Game', '加载词库失败', err);
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
    _bestMatch = 0;
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
    final savedPuzzlePath = prefs.getString(puzzlePathKey);
    final fallback = _embeddingService.onlineEndpoint.trim();
    final next = (saved ?? fallback).trim();
    _onlineEmbeddingUrl = next;
    _localEmbeddingDir = (savedLocal ?? '').trim();
    _puzzlePath = (savedPuzzlePath ?? '').trim();
    _embeddingService.onlineUrl = next;

    // 设置本地词库路径（如果有）
    if (_puzzlePath.isNotEmpty) {
      _puzzleRepository.setLocalPuzzlePath(_puzzlePath);
    }

    // 探测网络端点
    await _refreshConnectionStatus();

    // 如果没有本地词库路径，默认尝试服务器词库
    if (_puzzlePath.isEmpty && _connectionService.connectedPuzzleEndpoint != null) {
      _puzzleRepository.enableServerPuzzles();
      _puzzleRepository.setActiveEndpoint(_connectionService.connectedPuzzleEndpoint!);
      // 同时启用账号控制器连接服务器
      if (_accountController.puzzleMode == PuzzleMode.local) {
        unawaited(_accountController.connectToServerPuzzles());
      }
    }

    unawaited(refreshEmbeddingSourceLabel());
    notifyListeners();
  }

  /// 刷新连接状态，探测网络端点
  Future<void> _refreshConnectionStatus() async {
    ConnectionLog.info('Connection', '开始刷新连接状态');

    // 探测模型端点
    final embedResult = await _connectionService.probeEmbedEndpoints(
      lanEndpoints: ServerConfig.lanEmbedEndpoints,
      publicEndpoint: ServerConfig.publicEmbedEndpoint,
    );

    if (embedResult.status == ConnectionStatus.connected &&
        _connectionService.connectedEmbedEndpoint != null) {
      _embeddingService.onlineUrl = _connectionService.connectedEmbedEndpoint!;
      ConnectionLog.info('Connection', '模型端点连接成功', {
        'endpoint': _connectionService.connectedEmbedEndpoint!,
      });
    }

    // 探测词库端点
    final puzzleResult = await _connectionService.probePuzzleEndpoints(
      lanEndpoints: ServerConfig.lanPuzzleEndpoints,
      publicEndpoint: ServerConfig.publicPuzzleEndpoint,
    );

    if (puzzleResult.status == ConnectionStatus.connected &&
        _connectionService.connectedPuzzleEndpoint != null) {
      _puzzleRepository.setActiveEndpoint(_connectionService.connectedPuzzleEndpoint!);
      ConnectionLog.info('Connection', '词库端点连接成功', {
        'endpoint': _connectionService.connectedPuzzleEndpoint!,
      });
    }
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