import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

import '../models/guess_models.dart';

Color _scoreColor(int match) {
  if (match >= 95) return AppColors.scoreGold;
  if (match >= 80) return AppColors.scoreAmber;
  if (match >= 60) return AppColors.scoreGreen;
  if (match >= 30) return AppColors.primaryBlueBright;
  return AppColors.scoreGray;
}

Color _scoreBg(int match) {
  if (match >= 95) return AppColors.scoreGoldBg;
  if (match >= 80) return AppColors.scoreAmberBg;
  if (match >= 60) return AppColors.scoreGreenBg;
  if (match >= 30) return AppColors.primaryBlueSoft;
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
        final available = (constraints.maxHeight - totalGap).clamp(150.0, 1200.0);
        final resolvedExtent = itemExtent ?? (available / _visibleSlots);
        final rowHeight = resolvedExtent.clamp(24.0, 180.0);
        final badgeSize = rowHeight.clamp(20.0, 28.0);
        final verticalPadding = ((rowHeight - badgeSize) / 2).clamp(1.0, 10.0);
        final innerHeight = (rowHeight - verticalPadding * 2).clamp(20.0, 160.0);
        final wordFont = rowHeight < 38 ? 13.0 : 15.0;
        final scoreBigFont = rowHeight < 38 ? 17.0 : 21.0;
        final scoreSmallFont = rowHeight < 38 ? 10.0 : 11.0;
        final scoreIconSize = rowHeight < 38 ? 14.0 : 16.0;
        final compactScore = innerHeight < 36;

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
                padding: EdgeInsets.symmetric(horizontal: 12, vertical: verticalPadding),
                clipBehavior: Clip.antiAlias,
                decoration: BoxDecoration(
                  color: (hasData && slotItem != null) ? _scoreBg(slotItem.match) : (hasData ? AppColors.historyRow : AppColors.historyRowEmpty),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: hasData && slotItem != null ? _scoreColor(slotItem.match).withOpacity(0.3) : AppColors.historyRowBorder),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.start,
                  children: [
                    Container(
                      width: badgeSize,
                      height: badgeSize,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: AppColors.primaryBlueNotice,
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(
                        '${index + 1}',
                        style: AppTextStyles.historyBadge(badgeSize < 24 ? 12 : 13),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        slotItem?.word ?? '—',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: AppTextStyles.historyWord(
                          hasData: hasData,
                          fontSize: wordFont,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    if (slotItem != null)
                      SizedBox(
                        height: innerHeight,
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              crossAxisAlignment: CrossAxisAlignment.center,
                              children: [
                                Icon(
                                  Icons.bolt,
                                  color: _scoreColor(slotItem.match),
                                  size: scoreIconSize,
                                ),
                                const SizedBox(width: 4),
                                Text(
                                  '${slotItem.match}%',
                                  strutStyle: const StrutStyle(
                                    forceStrutHeight: true,
                                    height: 1.0,
                                  ),
                                  style: AppTextStyles.historyScore(scoreBigFont, color: _scoreColor(slotItem.match)),
                                ),
                              ],
                            ),
                            if (compactScore)
                              Text(
                                AppStrings.historyAssociationLabel(slotItem.match),
                                strutStyle: const StrutStyle(
                                  forceStrutHeight: true,
                                  height: 1.0,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: AppTextStyles.historyAssociation(scoreSmallFont),
                              )
                            else
                              Text(
                                '${AppStrings.historyAssociationLabel(slotItem.match)} · 关联度',
                                strutStyle: const StrutStyle(
                                  forceStrutHeight: true,
                                  height: 1.0,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: AppTextStyles.historyAssociation(scoreSmallFont),
                              ),
                          ],
                        ),
                      )
                    else
                      Text(
                        AppStrings.waitingInput,
                        style: AppTextStyles.waiting(scoreSmallFont),
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
}
