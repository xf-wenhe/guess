import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:guess/resources/resources.dart';
import 'package:path_provider/path_provider.dart';

import '../controllers/guess_game_controller.dart';
import '../models/guess_models.dart';
import '../services/embedding_service.dart';
import '../services/local_embedding_runner.dart';
import '../services/puzzle_repository.dart';
import '../utils/text_utils.dart';
import '../widgets/guess_hint_card.dart';
import '../widgets/guess_history_list.dart';
import '../widgets/guess_input_card.dart';
import '../widgets/guess_overlays.dart';
import '../widgets/guess_status_card.dart';
import '../widgets/result_dialog.dart';

part 'guess_home_page_actions.dart';
part 'guess_home_page_build.dart';

class GuessHomePage extends StatefulWidget {
  const GuessHomePage({super.key});

  @override
  State<GuessHomePage> createState() => _GuessHomePageState();
}

class _GuessHomePageState extends State<GuessHomePage>
    with TickerProviderStateMixin {
  static const List<int> _hintPercents = [30, 40, 50, 60, 70, 80, 90];

  late final GuessGameController _controller;
  late final LocalEmbeddingRunner _localRunner;
  final TextEditingController _textController = TextEditingController();
  final FocusNode _inputFocus = FocusNode();
  final ScrollController _historyScrollController = ScrollController();
  late final AnimationController _explosionController;
  late final AnimationController _winController;

  bool _showLoseResult = false;
  bool _showWinResult = false;
  bool _embeddingToastShown = false;
  bool _refreshingEmbedding = false;
  bool _localRunnerReady = false;
  bool _initializingLocalRunner = false;
  int _autoRefreshAttempts = 0;
  static const int _maxAutoRefreshAttempts = 3;
  String? _localRunnerError;
  bool _modelDownloadPending = false;
  bool _submitting = false;
  String? _statusTip;
  Timer? _statusTipTimer;

  @override
  void initState() {
    super.initState();
    _explosionController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    );
    _winController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    );

    _controller = GuessGameController(
      puzzleRepository: const PuzzleRepository(),
      embeddingService: EmbeddingService(
        localEndpoint: 'http://127.0.0.1:8000/embed',
        onlineEndpoint:
            const String.fromEnvironment('ONLINE_EMBEDDING_URL', defaultValue: ''),
        embeddingPrefix: '',
      ),
    )..addListener(_onControllerChanged);

    _controller.initialize();
    _initLocalEmbedding();
  }

  @override
  void dispose() {
    _controller
      ..removeListener(_onControllerChanged)
      ..dispose();
    if (_localRunnerReady) {
      _localRunner.stop();
    }
    _textController.dispose();
    _inputFocus.dispose();
    _historyScrollController.dispose();
    _statusTipTimer?.cancel();
    _explosionController.dispose();
    _winController.dispose();
    super.dispose();
  }

  void _showStatusTip(
    String message, {
    Duration duration = const Duration(seconds: 2),
  }) {
    _statusTipTimer?.cancel();
    _updateState(() {
      _statusTip = message;
    });
    _statusTipTimer = Timer(duration, () {
      if (!mounted) return;
      _updateState(() {
        _statusTip = null;
      });
    });
  }

  void _clearStatusTip() {
    _statusTipTimer?.cancel();
    _statusTipTimer = null;
    if (_statusTip == null) {
      return;
    }
    _updateState(() {
      _statusTip = null;
    });
  }

  void _onControllerChanged() {
    if (!mounted) return;
    if (_controller.embeddingSourceLabel != AppStrings.disconnectedSourceLabel) {
      _embeddingToastShown = false;
    }
    if (_controller.embeddingSourceLabel == AppStrings.disconnectedSourceLabel) {
      _maybeAutoRefresh();
    }
    setState(() {});
  }

  void _maybeAutoRefresh() {
    if (!_localRunnerReady) {
      return;
    }
    if (_refreshingEmbedding || _autoRefreshAttempts >= _maxAutoRefreshAttempts) {
      return;
    }
    _autoRefreshAttempts += 1;
    _refreshEmbedding(auto: true);
  }

  Future<void> _initLocalEmbedding() async {
    if (_initializingLocalRunner) {
      return;
    }
    _initializingLocalRunner = true;
    try {
      if (_localRunnerReady) {
        await _localRunner.stop();
      }
      final scriptPath = await _prepareLocalScriptPath();
      final localDir = _controller.localEmbeddingDir.trim();
      final resolvedLocalDir =
          localDir.isNotEmpty ? _resolveLocalModelDir(localDir) : null;
      final envOverrides = <String, String>{};
      if (resolvedLocalDir != null) {
        envOverrides['EMBED_MODEL_DIR'] = resolvedLocalDir;
      } else if (localDir.isNotEmpty) {
        _localRunnerError = AppStrings.modelConfigMissing;
      }
      _localRunner = LocalEmbeddingRunner(
        scriptPath: scriptPath,
        workingDirectory: File(scriptPath).parent.path,
        host: 'http://127.0.0.1:8000',
        envOverrides: envOverrides,
      );
      _localRunnerReady = true;
      _localRunnerError = null;
      if (mounted) {
        setState(() {});
      }
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _maybeAutoRefresh();
      });
    } catch (e) {
      _localRunnerError = AppStrings.localModelPrepareFailed(e);
      _showToast(AppStrings.localModelPrepareFailedToast);
    } finally {
      _initializingLocalRunner = false;
    }
  }

  Future<String> _prepareLocalScriptPath() async {
    final resolved = _localScriptPath();
    if (File(resolved).existsSync()) {
      return resolved;
    }
    final supportDir = await getApplicationSupportDirectory();
    final embedDir = Directory('${supportDir.path}${Platform.pathSeparator}embedding');
    if (!embedDir.existsSync()) {
      await embedDir.create(recursive: true);
    }
    final target = File(
      '${embedDir.path}${Platform.pathSeparator}${AppAssets.embeddingScript}',
    );
    if (!target.existsSync() || await target.length() == 0) {
      final data = await rootBundle.load(AppAssets.embeddingScript);
      await target.writeAsBytes(data.buffer.asUint8List(), flush: true);
    }
    final requirements = File(
      '${embedDir.path}${Platform.pathSeparator}${AppAssets.embeddingRequirements}',
    );
    if (!requirements.existsSync() || await requirements.length() == 0) {
      final data = await rootBundle.load(AppAssets.embeddingRequirements);
      await requirements.writeAsBytes(data.buffer.asUint8List(), flush: true);
    }
    final localDir = _controller.localEmbeddingDir.trim();
    if (localDir.isNotEmpty) {
      final resolved = _resolveLocalModelDir(localDir);
      if (resolved != null) {
        _modelDownloadPending = false;
      } else {
        _modelDownloadPending = false;
        _localRunnerError = AppStrings.modelConfigMissing;
      }
    } else {
      final modelConfig = File(
        '${embedDir.path}${Platform.pathSeparator}models'
        '${Platform.pathSeparator}bge-large-zh-noinstruct'
        '${Platform.pathSeparator}config.json',
      );
      _modelDownloadPending = !modelConfig.existsSync();
    }
    return target.path;
  }

  String? _resolveLocalModelDir(String input) {
    final base = Directory(input);
    if (!base.existsSync()) {
      return null;
    }
    final direct = File('${base.path}${Platform.pathSeparator}config.json');
    if (direct.existsSync()) {
      return base.path;
    }

    final queue = <Directory>[base];
    var depth = 0;
    const maxDepth = 4;
    while (queue.isNotEmpty && depth <= maxDepth) {
      final size = queue.length;
      for (var i = 0; i < size; i += 1) {
        final current = queue.removeAt(0);
        try {
          final entries = current.listSync(followLinks: true);
          for (final entry in entries) {
            if (entry is File && entry.path.endsWith('${Platform.pathSeparator}config.json')) {
              return entry.parent.path;
            }
            if (entry is Directory) {
              queue.add(entry);
            }
          }
        } catch (_) {
          // Ignore unreadable directories.
        }
      }
      depth += 1;
    }
    return null;
  }

  void _updateState(VoidCallback fn) {
    if (!mounted) return;
    setState(fn);
  }

  String _localScriptPath() {
    final sep = Platform.pathSeparator;
    const scriptName = AppAssets.embeddingScript;
    final override = Platform.environment['LOCAL_EMBEDDING_SCRIPT'];
    if (override != null && override.trim().isNotEmpty) {
      return override.trim();
    }

    final visited = <String>{};
    final anchors = <Directory>[
      Directory.current,
      File(Platform.resolvedExecutable).parent,
    ];
    final scriptUri = Platform.script;
    if (scriptUri.isScheme('file')) {
      anchors.add(File.fromUri(scriptUri).parent);
    }

    for (final anchor in anchors) {
      Directory dir = anchor;
      while (true) {
        if (visited.contains(dir.path)) {
          break;
        }
        visited.add(dir.path);
        final candidate = File('${dir.path}$sep$scriptName');
        if (candidate.existsSync()) {
          return candidate.path;
        }
        final parent = dir.parent;
        if (parent.path == dir.path) {
          break;
        }
        dir = parent;
      }
    }

    return '${Directory.current.path}$sep$scriptName';
  }

  @override
  Widget build(BuildContext context) {
    final current = _controller.current;
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        automaticallyImplyLeading: false,
        leadingWidth: _statusTip != null && _statusTip!.isNotEmpty ? 290 : 0,
        leading: _statusTip != null && _statusTip!.isNotEmpty
            ? Align(
                alignment: Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.only(left: 10),
                  child: Container(
                    constraints: const BoxConstraints(maxWidth: 270),
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: AppColors.primaryTealSoft,
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(color: AppColors.primaryTealBorder),
                    ),
                    child: Text(
                      _statusTip!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: AppTextStyles.statusTip,
                    ),
                  ),
                ),
              )
            : null,
        centerTitle: true,
        title: const Text(AppStrings.homeTitle),
        actions: [
          IconButton(
            tooltip: AppStrings.tooltipCheckConnection,
            onPressed: _refreshingEmbedding ? null : _refreshEmbedding,
            style: IconButton.styleFrom(
              backgroundColor: AppColors.primaryTealSoft,
              foregroundColor: AppColors.primaryTealDark,
            ),
            icon: const Icon(Icons.radar_outlined),
          ),
          const SizedBox(width: 2),
          IconButton(
            tooltip: AppStrings.tooltipModelSettings,
            onPressed: _showEmbeddingSettings,
            style: IconButton.styleFrom(
              backgroundColor: AppColors.primaryTealSoft,
              foregroundColor: AppColors.primaryTealDark,
            ),
            icon: const Icon(Icons.tune),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Stack(
        children: [
          Positioned.fill(
            child: Stack(
              children: [
                const DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        AppColors.decorMint,
                        AppColors.decorIvory,
                        AppColors.decorWarm,
                      ],
                    ),
                  ),
                ),
                Positioned(
                  top: -120,
                  right: -90,
                  child: Container(
                    width: 280,
                    height: 280,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: AppColors.seed.withOpacity(0.1),
                    ),
                  ),
                ),
                Positioned(
                  bottom: -130,
                  left: -100,
                  child: Container(
                    width: 300,
                    height: 300,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: AppColors.decorAmber.withOpacity(0.1),
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (_controller.loading)
            const Center(child: CircularProgressIndicator())
          else if (!_controller.hasPuzzles || current == null)
            _buildError()
          else
            _buildBody(current),
          if (_controller.won && current != null)
            WinOverlay(
              animation: _winController,
              showResult: _showWinResult,
              onReset: _resetGame,
              current: current,
              winBySemantic: _controller.winBySemantic,
              lastGuess: _controller.lastGuess,
            ),
          if (_controller.lost && current != null)
            LoseOverlay(
              animation: _explosionController,
              showResult: _showLoseResult,
              onReset: _resetGame,
              current: current,
            ),
        ],
      ),
    );
  }

}
