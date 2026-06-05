import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

import '../models/guess_models.dart';

/// 获取分数对应的霓虹色
Color _neonScoreColor(int match) {
  if (match >= 95) return AppColors.scoreGold;
  if (match >= 80) return AppColors.scoreAmber;
  if (match >= 60) return AppColors.scoreGreen;
  if (match >= 30) return AppColors.neonBlue;
  return AppColors.scoreGray;
}

/// 获取分数对应的发光阴影色
Color _neonScoreGlow(int match) {
  if (match >= 95) return AppColors.scoreGoldGlow;
  if (match >= 80) return AppColors.scoreAmberGlow;
  if (match >= 60) return AppColors.scoreGreenGlow;
  if (match >= 30) return AppColors.neonBlue.withOpacity(0.25);
  return AppColors.scoreGrayGlow;
}

/// 获取分数对应的背景色
Color _neonScoreBg(int match) {
  if (match >= 95) return AppColors.scoreGoldBg;
  if (match >= 80) return AppColors.scoreAmberBg;
  if (match >= 60) return AppColors.scoreGreenBg;
  if (match >= 30) return AppColors.neonBlue.withOpacity(0.12);
  return AppColors.scoreGrayBg;
}

class GuessHistoryList extends StatelessWidget {
  const GuessHistoryList({
    super.key,
    required this.history,
    required this.scrollController,
    this.itemExtent,
  });

  static const int _visibleSlots = 6;

  final List<GuessResult> history;
  final ScrollController scrollController;
  final double? itemExtent;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const gap = 8.0;
        const totalGap = gap * (_visibleSlots - 1);
        final available =
            (constraints.maxHeight - totalGap).clamp(150.0, 1200.0);
        final resolvedExtent = itemExtent ?? (available / _visibleSlots);
        final rowHeight = resolvedExtent.clamp(24.0, 180.0);
        final badgeSize = rowHeight.clamp(20.0, 28.0);
        final verticalPadding =
            ((rowHeight - badgeSize) / 2).clamp(1.0, 10.0);
        final wordFont = rowHeight < 38 ? 13.0 : 15.0;
        final scoreBigFont = rowHeight < 38 ? 17.0 : 21.0;
        final scoreSmallFont = rowHeight < 38 ? 10.0 : 11.0;
        final scoreIconSize = rowHeight < 38 ? 14.0 : 16.0;

        return Column(
          children: List.generate(_visibleSlots * 2 - 1, (idx) {
            if (idx.isOdd) {
              return const SizedBox(height: gap);
            }
            final index = idx ~/ 2;
            final hasData = index < history.length;
            final GuessResult? slotItem = hasData ? history[index] : null;

            return SizedBox(
              height: rowHeight,
              child: Container(
                padding:
                    EdgeInsets.symmetric(horizontal: 12, vertical: verticalPadding),
                clipBehavior: Clip.antiAlias,
                decoration: BoxDecoration(
                  color: (hasData && slotItem != null)
                      ? _neonScoreBg(slotItem.match)
                      : AppColors.historyRowEmpty,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(
                    color: hasData && slotItem != null
                        ? _neonScoreColor(slotItem.match).withOpacity(0.25)
                        : AppColors.historyRowBorder,
                  ),
                  boxShadow: hasData && slotItem != null
                      ? [
                          BoxShadow(
                            color: _neonScoreGlow(slotItem.match),
                            blurRadius: 8,
                            spreadRadius: 0,
                          ),
                        ]
                      : null,
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.start,
                  children: [
                    // 序号徽章
                    Container(
                      width: badgeSize,
                      height: badgeSize,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: hasData && slotItem != null
                              ? [
                                  _neonScoreColor(slotItem.match).withOpacity(0.3),
                                  _neonScoreColor(slotItem.match).withOpacity(0.1),
                                ]
                              : [
                                  Colors.white.withOpacity(0.08),
                                  Colors.white.withOpacity(0.04),
                                ],
                        ),
                        borderRadius: BorderRadius.circular(999),
                        border: Border.all(
                          color: hasData && slotItem != null
                              ? _neonScoreColor(slotItem.match).withOpacity(0.4)
                              : Colors.white.withOpacity(0.1),
                        ),
                      ),
                      child: Text(
                        '${index + 1}',
                        style: TextStyle(
                          fontFamily: AppFonts.primaryFamily,
                          fontSize: badgeSize < 24 ? 12 : 13,
                          color: hasData && slotItem != null
                              ? _neonScoreColor(slotItem.match)
                              : AppColors.textMuted,
                          fontWeight: AppFonts.extraBold,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    // 猜测词
                    Expanded(
                      child: Text(
                        slotItem?.word ?? '—',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontFamily: AppFonts.primaryFamily,
                          fontSize: wordFont,
                          color: hasData
                              ? AppColors.textPrimary
                              : AppColors.textMuted,
                          fontWeight: AppFonts.bold,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    // 分数区域
                    if (slotItem != null)
                      _buildScoreSection(
                        slotItem,
                        scoreBigFont,
                        scoreSmallFont,
                        scoreIconSize,
                      )
                    else
                      Text(
                        AppStrings.waitingInput,
                        style: TextStyle(
                          fontFamily: AppFonts.primaryFamily,
                          fontSize: scoreSmallFont,
                          color: AppColors.textMuted,
                          fontWeight: AppFonts.semibold,
                        ),
                      ),
                  ],
                ),
              ),
            );
          }),
        );
      },
    );
  }

  Widget _buildScoreSection(
    GuessResult item,
    double bigFont,
    double smallFont,
    double iconSize,
  ) {
    final color = _neonScoreColor(item.match);

    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Icon(Icons.bolt, color: color, size: iconSize),
            const SizedBox(width: 2),
            Flexible(
              child: Text(
                '${item.match}%',
                strutStyle: const StrutStyle(
                  forceStrutHeight: true,
                  height: 1.0,
                ),
                style: TextStyle(
                  fontFamily: AppFonts.primaryFamily,
                  fontSize: bigFont,
                  color: color,
                  fontWeight: AppFonts.extraBold,
                  height: 1.0,
                  shadows: [
                    Shadow(
                      color: color.withOpacity(0.5),
                      blurRadius: 8,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
        Text(
          '${AppStrings.historyAssociationLabel(item.match)} · 关联度',
          strutStyle: const StrutStyle(
            forceStrutHeight: true,
            height: 1.0,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontFamily: AppFonts.primaryFamily,
            fontSize: smallFont,
            color: AppColors.textSecondary,
            fontWeight: AppFonts.semibold,
            height: 1.0,
          ),
        ),
      ],
    );
  }
}
