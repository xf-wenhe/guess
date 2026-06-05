part of 'guess_home_page.dart';

extension _GuessHomePageBuild on _GuessHomePageState {
  Widget _buildBody(GuessPuzzle current) {
    return SafeArea(
      child: GestureDetector(
        behavior: HitTestBehavior.translucent,
        onTap: () {
          if (!_controller.inputDisabled) {
            _focusInput();
          }
        },
        child: LayoutBuilder(
          builder: (context, constraints) {
            final narrow = constraints.maxWidth < 860;
            return Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 880),
                child: SizedBox(
                  height: constraints.maxHeight,
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(
                      narrow ? 10 : 14,
                      6,
                      narrow ? 10 : 14,
                      8,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                      if (_refreshingEmbedding)
                        _buildNotice(
                          message: AppStrings.connectionInProgress,
                          background: AppColors.primaryBlueNotice,
                          border: AppColors.primaryBlueNoticeBorder,
                          textColor: AppColors.primaryBlueNoticeText,
                        ),
                      if (_refreshingEmbedding) const SizedBox(height: 8),
                      if (_modelDownloadPending)
                        _buildNotice(
                          message: AppStrings.initialDownloadHint,
                          background: AppColors.warningBg,
                          border: AppColors.warningBorder,
                          textColor: AppColors.warningText,
                        ),
                      if (_modelDownloadPending) const SizedBox(height: 8),
                      if (_controller.embeddingSourceLabel ==
                              AppStrings.disconnectedSourceLabel &&
                          _localRunnerError != null)
                        _buildNotice(
                          message: _localRunnerError!,
                          background: AppColors.dangerNoticeBg,
                          border: AppColors.dangerNoticeBorder,
                          textColor: AppColors.dangerText,
                        ),
                      if (_controller.embeddingSourceLabel ==
                              AppStrings.disconnectedSourceLabel &&
                          _localRunnerError != null)
                        const SizedBox(height: 8),
                      GuessStatusCard(
                        attemptsLeft: _controller.attemptsLeft,
                        embeddingSourceLabel: _controller.embeddingSourceLabel,
                        categoryUnlocked: _controller.categoryUnlocked,
                        lengthUnlocked: _controller.lengthUnlocked,
                        posUnlocked: _controller.posUnlocked,
                        current: current,
                        puzzleMode: _accountController.puzzleMode,
                      ),
                      const SizedBox(height: 6),
                      Expanded(
                        child: LayoutBuilder(builder: (context, constraints) {
                            if (constraints.maxHeight < 420 && !narrow) {
                              return Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Expanded(
                                    flex: 1,
                                    child: _buildHintPanel(current),
                                  ),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    flex: 1,
                                    child: _buildHistoryPanel(),
                                  ),
                                ],
                              );
                            }
                            return Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Expanded(
                                  flex: 1,
                                  child: SizedBox(
                                    height: constraints.maxHeight,
                                    child: _buildHintPanel(
                                      current,
                                      panelHeight: constraints.maxHeight,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  flex: 1,
                                  child: SizedBox(
                                    height: constraints.maxHeight,
                                    child: _buildHistoryPanel(),
                                  ),
                                ),
                              ],
                            );
                        }),
                      ),
                      const SizedBox(height: 6),
                      GuessInputCard(
                        controller: _textController,
                        focusNode: _inputFocus,
                        inputDisabled: _controller.inputDisabled,
                        submitting: _submitting,
                        submitDisabled: _controller.inputDisabled ||
                            _submitting ||
                            _refreshingEmbedding,
                        onSubmit: _submitGuess,
                      ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildHistoryPanel() {
    return _GlassPanel(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildPanelHeader(
              icon: Icons.track_changes_rounded,
              iconColor: AppColors.neonBlue,
              background: AppColors.neonBlue.withOpacity(0.15),
              label: AppStrings.historyTitle,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: _HistoryMetaChip(
                    icon: Icons.numbers,
                    label: AppStrings.guessedCount(_controller.history.length),
                  ),
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: _HistoryMetaChip(
                    icon: Icons.local_fire_department_outlined,
                    label: AppStrings.bestMatch(_controller.bestMatch),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Expanded(
              child: GuessHistoryList(
                history: _controller.history,
                scrollController: _historyScrollController,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHintPanel(GuessPuzzle current, {double? panelHeight}) {
    return _GlassPanel(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final hintHeight = (constraints.maxHeight - 34)
                .clamp(120.0, constraints.maxHeight)
                .toDouble();
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildPanelHeader(
                  icon: Icons.lightbulb_outline_rounded,
                  iconColor: AppColors.neonAmber,
                  background: AppColors.neonAmber.withOpacity(0.15),
                  label: AppStrings.hintTitle,
                ),
                const SizedBox(height: 6),
                Expanded(
                  child: GuessHintCard(
                    hints: current.hints,
                    hintIndex: _controller.hintIndex,
                    hintPercents: _GuessHomePageState._hintPercents,
                    fixedHeight: hintHeight,
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _buildPanelHeader({
    required IconData icon,
    required Color iconColor,
    required Color background,
    required String label,
  }) {
    return Row(
      children: [
        Container(
          width: 28,
          height: 28,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [iconColor.withOpacity(0.2), iconColor.withOpacity(0.05)],
            ),
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: iconColor.withOpacity(0.3)),
          ),
          child: Icon(icon, size: 17, color: iconColor),
        ),
        const SizedBox(width: 8),
        Text(
          label,
          style: AppTextStyles.panelTitle,
        ),
      ],
    );
  }

  Widget _buildError() {
    final puzzleError = _controller.puzzleLoadError;
    if (puzzleError != null && puzzleError.isNotEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: PuzzleErrorBanner(
            error: puzzleError,
            onRetry: () => _controller.reloadPuzzles(),
            onConnectServer: () async {
              // 1. 连接账号服务
              final success = await _accountController.connectToServerPuzzles();
              if (!success) {
                _showToast('连接服务器失败');
                return;
              }
              // 2. 如果是新用户，弹出昵称对话框
              if (_accountController.user == null) {
                if (!mounted) return;
                await AccountCreationDialog.show(
                  context,
                  onSubmit: _accountController.createAccount,
                );
                // 检查是否创建成功
                if (_accountController.user == null) {
                  // 用户取消了昵称输入，重置状态
                  _accountController.resetSession();
                  return;
                }
              }
              // 3. 启用服务器词库并重新加载
              await _controller.enableServerPuzzlesAndReload();
            },
          ),
        ),
      );
    }
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            AppStrings.loadPuzzleFailed,
            style: AppTextStyles.dialogGuess,
          ),
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: _controller.reloadPuzzles,
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primaryBlueDark,
              foregroundColor: AppColors.white,
            ),
            child: const Text(AppStrings.reload),
          ),
        ],
      ),
    );
  }

  Widget _buildNotice({
    required String message,
    required Color background,
    required Color border,
    required Color textColor,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: border),
      ),
      child: Text(
        message,
        style: TextStyle(
          fontFamily: AppFonts.primaryFamily,
          fontSize: 12,
          color: textColor,
          fontWeight: AppFonts.semibold,
        ),
      ),
    );
  }
}

/// 玻璃态面板组件
class _GlassPanel extends StatelessWidget {
  const _GlassPanel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: Stack(
        children: [
          // 背景模糊层
          Positioned.fill(
            child: Container(
              decoration: BoxDecoration(
                color: AppColors.glassPanelBg,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: AppColors.glassPanelBorder,
                  width: 1,
                ),
              ),
            ),
          ),
          // 顶部高光
          Positioned(
            top: 0,
            left: 20,
            right: 20,
            child: Container(
              height: 1,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    Colors.white.withOpacity(0),
                    Colors.white.withOpacity(0.15),
                    Colors.white.withOpacity(0),
                  ],
                ),
              ),
            ),
          ),
          // 内容
          child,
        ],
      ),
    );
  }
}

class _HistoryMetaChip extends StatelessWidget {
  const _HistoryMetaChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 32,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: AppColors.neonBlue.withOpacity(0.1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: AppColors.neonBlue.withOpacity(0.2)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 16, color: AppColors.neonBlue),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontFamily: AppFonts.primaryFamily,
                fontSize: 13,
                color: AppColors.neonBlue,
                fontWeight: AppFonts.bold,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
