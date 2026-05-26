import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

import '../models/guess_models.dart';

class GuessStatusCard extends StatelessWidget {
  const GuessStatusCard({
    super.key,
    required this.attemptsLeft,
    required this.embeddingSourceLabel,
    required this.categoryUnlocked,
    required this.lengthUnlocked,
    required this.posUnlocked,
    required this.current,
  });

  final int attemptsLeft;
  final String embeddingSourceLabel;
  final bool categoryUnlocked;
  final bool lengthUnlocked;
  final bool posUnlocked;
  final GuessPuzzle current;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final headlineStyle = AppTextStyles.statusHeadline(textTheme.headlineSmall);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(8, 5, 8, 5),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppColors.primaryBlue, AppColors.primaryBlueBright],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(18),
        boxShadow: const [
          BoxShadow(
            color: AppColors.primaryBlueShadow,
            blurRadius: 14,
            offset: Offset(0, 6),
          ),
        ],
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final compact = constraints.maxWidth < 760;
          final infoSection = compact
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _buildSection(
                      child: _buildAttemptsInfo(headlineStyle),
                      alignment: Alignment.centerLeft,
                    ),
                    const SizedBox(height: 4),
                    _buildSection(
                      child: _buildRightInfo(compact: true),
                      alignment: Alignment.centerLeft,
                    ),
                  ],
                )
              : IntrinsicHeight(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(
                        child: _buildSection(
                          child: _buildAttemptsInfo(headlineStyle),
                          alignment: Alignment.centerLeft,
                        ),
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: _buildSection(
                          child: _buildRightInfo(compact: false),
                          alignment: Alignment.centerRight,
                        ),
                      ),
                    ],
                  ),
                );

          return infoSection;
        },
      ),
    );
  }

  Widget _buildSection({
    required Widget child,
    required Alignment alignment,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: AppColors.white.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.white.withOpacity(0.2)),
      ),
      child: Align(alignment: alignment, child: child),
    );
  }

  Widget _buildAttemptsInfo(TextStyle headlineStyle) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text(
          AppStrings.attemptsLeft,
          style: AppTextStyles.statusSectionLabel,
        ),
        const SizedBox(height: 1),
        Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              '$attemptsLeft',
              style: headlineStyle,
            ),
            const SizedBox(width: 4),
            const Padding(
              padding: EdgeInsets.only(bottom: 2),
              child: Text(
                AppStrings.attemptsUnit,
                style: AppTextStyles.statusUnit,
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        _AttemptDots(attemptsLeft: attemptsLeft),
        const Text(
          AppStrings.totalAttempts,
          style: AppTextStyles.statusCaption,
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
              style: AppTextStyles.statusSectionLabel,
            ),
            const SizedBox(width: 6),
            _InfoPill(label: AppStrings.modelLabel(embeddingSourceLabel)),
          ],
        ),
        if (categoryUnlocked) ...[
          const SizedBox(height: 2),
          Wrap(
            direction: Axis.horizontal,
            spacing: 5,
            runSpacing: 3,
            alignment: compact ? WrapAlignment.start : WrapAlignment.end,
            children: [
              _InfoPill(label: AppStrings.rangeLabel(current.category)),
              if (lengthUnlocked)
                _InfoPill(label: AppStrings.lengthLabel(current.answer.length)),
              if (posUnlocked) _InfoPill(label: AppStrings.posLabel(current.pos)),
            ],
          ),
        ] else ...[
          const SizedBox(height: 3),
          const Text(
            AppStrings.unlockMoreHints,
            style: AppTextStyles.statusPrompt,
          ),
        ],
      ],
    );
  }
}

class _AttemptDots extends StatelessWidget {
  const _AttemptDots({required this.attemptsLeft});

  final int attemptsLeft;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(6, (i) {
        final used = i >= attemptsLeft;
        return Container(
          width: 6,
          height: 6,
          margin: const EdgeInsets.only(right: 4),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: used
                ? AppColors.white.withOpacity(0.25)
                : AppColors.white,
          ),
        );
      }),
    );
  }
}

class _InfoPill extends StatelessWidget {
  const _InfoPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.white.withOpacity(0.2),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: AppColors.white.withOpacity(0.35)),
      ),
      child: Text(
        label,
        style: AppTextStyles.infoPill,
      ),
    );
  }
}
