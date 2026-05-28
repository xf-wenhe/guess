part of 'guess_home_page.dart';

extension _GuessHomePageActions on _GuessHomePageState {
  void _focusInput() {
    if (_inputFocus.canRequestFocus) {
      _inputFocus.requestFocus();
    }
  }

  Future<void> _submitGuess() async {
    if (_controller.inputDisabled || _submitting || _refreshingEmbedding) {
      return;
    }
    final raw = _textController.text.trim();
    if (raw.isEmpty || raw.length < 2 || raw.length > 5) {
      _showStatusTip(AppStrings.invalidGuess);
      _focusInput();
      return;
    }
    if (!isAllChinese(raw)) {
      _showStatusTip(AppStrings.invalidGuess);
      _focusInput();
      return;
    }
    if (_controller.hasGuessed(raw)) {
      _showStatusTip(AppStrings.duplicatedGuess);
      _focusInput();
      return;
    }
    _updateState(() {
      _submitting = true;
    });
    _inputFocus.unfocus();

    try {
      final outcome = await _controller.evaluateGuess(raw);
      if (!mounted) return;
      await _showResultDialog(raw, outcome.similarity);

      final applyResult = _controller.applyGuess(raw, outcome);
      if (applyResult.becameLose) {
        _triggerLoseAnimation();
      }
      if (applyResult.becameWin) {
        _triggerWinAnimation();
      }

      if (_controller.embeddingSourceLabel ==
              AppStrings.disconnectedSourceLabel &&
          !_embeddingToastShown) {
        _embeddingToastShown = true;
        _showStatusTip(AppStrings.semanticFallback);
      }

      if (!outcome.isWin && outcome.similarity >= 70) {
        _showStatusTip(AppStrings.almostThere);
      } else {
        _showStatusTip(AppStrings.guessFeedback(raw, outcome.similarity));
      }
      _textController.clear();
      _focusInput();
    } catch (_) {
      if (mounted) {
        _showStatusTip(AppStrings.submitFailed);
      }
    } finally {
      if (mounted) {
        _updateState(() {
          _submitting = false;
        });
      }
    }
  }

  void _triggerLoseAnimation() {
    _showLoseResult = false;
    _explosionController.forward(from: 0);
    Future<void>.delayed(const Duration(seconds: 2), () {
      if (mounted && _controller.lost) {
        _updateState(() {
          _showLoseResult = true;
        });
      }
    });
  }

  void _triggerWinAnimation() {
    _showWinResult = false;
    _winController.forward(from: 0);
    Future<void>.delayed(const Duration(seconds: 2), () {
      if (mounted && _controller.won) {
        _updateState(() {
          _showWinResult = true;
        });
      }
    });
  }

  Future<void> _showResultDialog(String guess, int similarity) async {
    if (!mounted) return;
    await showGeneralDialog<void>(
      context: context,
      barrierDismissible: true,
      barrierLabel: AppStrings.resultBarrierLabel,
      barrierColor: Colors.black87,
      transitionDuration: const Duration(milliseconds: 220),
      pageBuilder: (context, _, __) {
        return ResultDialog(guess: guess, similarity: similarity);
      },
      transitionBuilder: (context, animation, _, child) {
        final curved =
            CurvedAnimation(parent: animation, curve: Curves.easeOutBack);
        return FadeTransition(
          opacity: animation,
          child: ScaleTransition(scale: curved, child: child),
        );
      },
    );
  }

  void _showToast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  Future<void> _showEmbeddingSettings() async {
    final controller =
        TextEditingController(text: _controller.onlineEmbeddingUrl);
    final localController =
        TextEditingController(text: _controller.localEmbeddingDir);
    final result = await showModalBottomSheet<Map<String, String>>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      backgroundColor: const Color(0xFF1A1A2E),
      builder: (context) {
        final bottomInset = MediaQuery.of(context).viewInsets.bottom;
        return Padding(
          padding: EdgeInsets.only(
            left: 16,
            right: 16,
            top: 16,
            bottom: bottomInset + 16,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                AppStrings.localModelDir,
                style: TextStyle(
                  fontFamily: AppFonts.primaryFamily,
                  fontSize: 16,
                  color: AppColors.textPrimary,
                  fontWeight: AppFonts.bold,
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: localController,
                style: const TextStyle(color: AppColors.textPrimary),
                decoration: InputDecoration(
                  hintText: AppStrings.localModelDirHint,
                  hintStyle: const TextStyle(color: AppColors.textMuted),
                  filled: true,
                  fillColor: Colors.white.withOpacity(0.06),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide.none,
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: AppColors.neonCyan),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                AppStrings.localModelDirCaption,
                style: TextStyle(
                  fontFamily: AppFonts.primaryFamily,
                  fontSize: 12,
                  color: AppColors.textSecondary,
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                AppStrings.onlineModelUrl,
                style: TextStyle(
                  fontFamily: AppFonts.primaryFamily,
                  fontSize: 16,
                  color: AppColors.textPrimary,
                  fontWeight: AppFonts.bold,
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: controller,
                style: const TextStyle(color: AppColors.textPrimary),
                decoration: InputDecoration(
                  hintText: AppStrings.onlineModelUrlHint,
                  hintStyle: const TextStyle(color: AppColors.textMuted),
                  filled: true,
                  fillColor: Colors.white.withOpacity(0.06),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide.none,
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: AppColors.neonCyan),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                AppStrings.onlineModelUrlCaption,
                style: TextStyle(
                  fontFamily: AppFonts.primaryFamily,
                  fontSize: 12,
                  color: AppColors.textSecondary,
                ),
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: TextButton.styleFrom(
                      foregroundColor: AppColors.textSecondary,
                    ),
                    child: const Text(AppStrings.cancel),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton(
                    onPressed: () => Navigator.of(context).pop({
                      'online': controller.text.trim(),
                      'local': localController.text.trim(),
                    }),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.neonCyan,
                      foregroundColor: const Color(0xFF1A1A2E),
                    ),
                    child: const Text(AppStrings.save),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
    if (result == null) return;
    final online = result['online'] ?? '';
    final local = result['local'] ?? '';
    await _controller.updateOnlineEmbeddingUrl(online.trim());
    await _controller.updateLocalEmbeddingDir(local.trim());
    await _initLocalEmbedding();
    _maybeAutoRefresh();
  }

  Future<void> _refreshEmbedding({bool auto = false}) async {
    if (!_localRunnerReady) {
      _showToast(AppStrings.localModelNotReady);
      return;
    }
    if (_refreshingEmbedding) return;
    _updateState(() {
      _refreshingEmbedding = true;
      _embeddingToastShown = false;
    });
    try {
      final pendingDownload = _modelDownloadPending;
      final ready = await _localRunner
          .restartAndWait(
            timeout: auto
                ? (pendingDownload
                    ? const Duration(minutes: 10)
                    : const Duration(seconds: 90))
                : (pendingDownload
                    ? const Duration(minutes: 5)
                    : const Duration(seconds: 25)),
          )
          .timeout(
            auto
                ? (pendingDownload
                    ? const Duration(minutes: 12)
                    : const Duration(seconds: 120))
                : (pendingDownload
                    ? const Duration(minutes: 6)
                    : const Duration(seconds: 35)),
          );
      if (!ready) {
        final startError = _localRunner.lastError;
        if (startError != null && startError.isNotEmpty) {
          _localRunnerError = startError;
          _showToast(startError);
        } else {
          _localRunnerError = AppStrings.localModelStartFailed;
          _showToast(AppStrings.localModelStartFailed);
        }
        await _controller.refreshEmbeddingSourceLabel();
        if (auto) {
          Future<void>.delayed(const Duration(seconds: 5), () {
            if (mounted) {
              _maybeAutoRefresh();
            }
          });
        }
        return;
      }
      _localRunnerError = null;

      const maxAttempts = 30;
      for (var attempt = 0; attempt < maxAttempts; attempt += 1) {
        await _controller.refreshEmbeddingSourceLabel();
        if (_controller.embeddingSourceLabel !=
            AppStrings.disconnectedSourceLabel) {
          break;
        }
        await Future<void>.delayed(const Duration(milliseconds: 800));
      }
      if (_controller.embeddingSourceLabel ==
          AppStrings.disconnectedSourceLabel) {
        _localRunnerError =
            _localRunner.lastError ?? AppStrings.localModelPortNotReady;
        _showToast(AppStrings.localModelPortNotReady);
        if (auto) {
          Future<void>.delayed(const Duration(seconds: 5), () {
            if (mounted) {
              _maybeAutoRefresh();
            }
          });
        }
      } else {
        _modelDownloadPending = false;
        _localRunnerError = null;
        _showToast(
            AppStrings.currentModelLabel(_controller.embeddingSourceLabel));
        if (auto) {
          _autoRefreshAttempts = 0;
        }
      }
    } on TimeoutException {
      _localRunnerError = AppStrings.localModelTimeout;
      _showToast(_localRunnerError!);
    } finally {
      if (mounted) {
        _updateState(() {
          _refreshingEmbedding = false;
        });
      }
    }
  }

  void _resetGame() {
    _controller.resetGame();
    _clearStatusTip();
    _textController.clear();
    _focusInput();
  }
}
