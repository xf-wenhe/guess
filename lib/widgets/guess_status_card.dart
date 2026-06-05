import 'dart:math';
import 'package:flutter/material.dart';
import 'package:guess/controllers/account_controller.dart';
import 'package:guess/resources/resources.dart';

import '../models/guess_models.dart';

/// 顶部状态卡 — 霓虹渐变 + 光晕动画
class GuessStatusCard extends StatefulWidget {
  const GuessStatusCard({
    super.key,
    required this.attemptsLeft,
    required this.embeddingSourceLabel,
    required this.categoryUnlocked,
    required this.lengthUnlocked,
    required this.posUnlocked,
    required this.current,
    required this.puzzleMode,
  });

  final int attemptsLeft;
  final String embeddingSourceLabel;
  final bool categoryUnlocked;
  final bool lengthUnlocked;
  final bool posUnlocked;
  final GuessPuzzle current;
  final PuzzleMode puzzleMode;

  @override
  State<GuessStatusCard> createState() => _GuessStatusCardState();
}

class _GuessStatusCardState extends State<GuessStatusCard>
    with SingleTickerProviderStateMixin {
  late final AnimationController _shimmerController;

  @override
  void initState() {
    super.initState();
    _shimmerController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat();
  }

  @override
  void dispose() {
    _shimmerController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _shimmerController,
      builder: (context, _) {
        final shimmerT = _shimmerController.value;

        return Container(
          width: double.infinity,
          padding: const EdgeInsets.all(2), // 边框留白
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            // 外层发光边框
            gradient: LinearGradient(
              colors: [
                AppColors.neonPurple.withOpacity(0.5 + sin(shimmerT * pi * 2) * 0.2),
                AppColors.neonCyan.withOpacity(0.5 + cos(shimmerT * pi * 2) * 0.2),
                AppColors.neonPink.withOpacity(0.5 + sin(shimmerT * pi * 2 + 1) * 0.2),
              ],
            ),
            boxShadow: [
              BoxShadow(
                color: AppColors.neonPurple.withOpacity(0.15),
                blurRadius: 20,
                spreadRadius: 1,
              ),
              BoxShadow(
                color: AppColors.neonCyan.withOpacity(0.1),
                blurRadius: 30,
                spreadRadius: 2,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Container(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(20),
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  const Color(0xFF1A1050),
                  const Color(0xFF0F2040),
                  const Color(0xFF1A1050).withOpacity(0.9),
                ],
              ),
            ),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final compact = constraints.maxWidth < 760;
                final infoSection = compact
                    ? Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          _buildSection(
                            child: _buildAttemptsInfo(shimmerT),
                            alignment: Alignment.centerLeft,
                          ),
                          const SizedBox(height: 6),
                          _buildSection(
                            child: _buildRightInfo(compact: true),
                            alignment: Alignment.centerLeft,
                          ),
                        ],
                      )
                    : Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: _buildSection(
                              child: _buildAttemptsInfo(shimmerT),
                              alignment: Alignment.centerLeft,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: _buildSection(
                              child: _buildRightInfo(compact: false),
                              alignment: Alignment.centerRight,
                            ),
                          ),
                        ],
                      );

                return infoSection;
              },
            ),
          ),
        );
      },
    );
  }

  Widget _buildSection({
    required Widget child,
    required Alignment alignment,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.06),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.white.withOpacity(0.1)),
      ),
      child: Align(alignment: alignment, child: child),
    );
  }

  Widget _buildAttemptsInfo(double shimmerT) {
    // 生成动态颜色
    final glowColor = Color.lerp(
      AppColors.neonCyan,
      AppColors.neonPurple,
      (sin(shimmerT * pi * 2) + 1) / 2,
    )!;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text(
          AppStrings.attemptsLeft,
          style: TextStyle(
            fontFamily: AppFonts.primaryFamily,
            color: AppColors.textStatusLight,
            fontSize: 11,
            letterSpacing: 0.5,
          ),
        ),
        const SizedBox(height: 2),
        Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            ShaderMask(
              shaderCallback: (bounds) => LinearGradient(
                colors: [glowColor, AppColors.neonCyan],
              ).createShader(bounds),
              child: Text(
                '${widget.attemptsLeft}',
                style: const TextStyle(
                  fontFamily: AppFonts.primaryFamily,
                  fontSize: 32,
                  height: 0.9,
                  fontWeight: AppFonts.extraBold,
                  color: Colors.white,
                ),
              ),
            ),
            const SizedBox(width: 4),
            const Padding(
              padding: EdgeInsets.only(bottom: 3),
              child: Text(
                AppStrings.attemptsUnit,
                style: TextStyle(
                  fontFamily: AppFonts.primaryFamily,
                  color: AppColors.textStatusLight,
                  fontSize: 15,
                  fontWeight: AppFonts.bold,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        _AttemptDots(attemptsLeft: widget.attemptsLeft, glowColor: glowColor),
        const SizedBox(height: 2),
        const Text(
          AppStrings.totalAttempts,
          style: TextStyle(
            fontFamily: AppFonts.primaryFamily,
            color: AppColors.textStatusLight,
            fontSize: 10,
            fontWeight: AppFonts.semibold,
          ),
        ),
      ],
    );
  }

  Widget _buildRightInfo({required bool compact}) {
    final cross = compact ? CrossAxisAlignment.start : CrossAxisAlignment.end;
    return Column(
      crossAxisAlignment: cross,
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              AppStrings.answerInfo,
              style: TextStyle(
                fontFamily: AppFonts.primaryFamily,
                color: AppColors.textStatusLight,
                fontSize: 11,
              ),
            ),
            const SizedBox(width: 6),
            // 根据词库模式显示不同状态
            if (widget.puzzleMode == PuzzleMode.server)
              const _InfoPill(label: AppStrings.serverConnected),
          ],
        ),
        if (widget.categoryUnlocked) ...[
          const SizedBox(height: 4),
          Wrap(
            direction: Axis.horizontal,
            spacing: 6,
            runSpacing: 4,
            alignment: compact ? WrapAlignment.start : WrapAlignment.end,
            children: [
              _InfoPill(label: AppStrings.rangeLabel(widget.current.category)),
              if (widget.lengthUnlocked)
                _InfoPill(
                    label: AppStrings.lengthLabel(widget.current.answer.length)),
              if (widget.posUnlocked)
                _InfoPill(label: AppStrings.posLabel(widget.current.pos)),
            ],
          ),
        ] else ...[
          const SizedBox(height: 4),
          const Text(
            AppStrings.unlockMoreHints,
            style: TextStyle(
              fontFamily: AppFonts.primaryFamily,
              color: AppColors.textStatusLight,
              fontSize: 11,
              fontWeight: AppFonts.medium,
            ),
          ),
        ],
      ],
    );
  }
}

/// 剩余次数圆点指示器
class _AttemptDots extends StatelessWidget {
  const _AttemptDots({required this.attemptsLeft, required this.glowColor});

  final int attemptsLeft;
  final Color glowColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(6, (i) {
        final used = i >= attemptsLeft;
        final isLast = i == attemptsLeft - 1;
        return Container(
          width: 7,
          height: 7,
          margin: const EdgeInsets.only(right: 5),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: used
                ? Colors.white.withOpacity(0.15)
                : Colors.white,
            boxShadow: !used && isLast
                ? [
                    BoxShadow(
                      color: glowColor.withOpacity(0.6),
                      blurRadius: 6,
                      spreadRadius: 1,
                    ),
                  ]
                : null,
          ),
        );
      }),
    );
  }
}

/// 信息标签
class _InfoPill extends StatelessWidget {
  const _InfoPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            Colors.white.withOpacity(0.12),
            Colors.white.withOpacity(0.06),
          ],
        ),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withOpacity(0.2)),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontFamily: AppFonts.primaryFamily,
          color: Colors.white,
          fontSize: 11,
          fontWeight: AppFonts.bold,
        ),
      ),
    );
  }
}
