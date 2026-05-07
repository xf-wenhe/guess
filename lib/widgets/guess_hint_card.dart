import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

class GuessHintCard extends StatelessWidget {
  final List<String> hints;
  final int hintIndex;
  final List<int> hintPercents;
  final double? fixedHeight;

  const GuessHintCard({
    super.key,
    required this.hints,
    required this.hintIndex,
    required this.hintPercents,
    this.fixedHeight,
  });

  @override
  Widget build(BuildContext context) {
    const int total = 7;
    const double gap = 6;
    final double height = fixedHeight ?? 320;
    const List<double> weights = [1.15, 1.10, 0.95, 0.95, 0.95, 0.95, 0.95];
    final double baseHeight = (height - gap * (total - 1)) / 7.0;
    final List<String> visibleHints = List.generate(total, (i) => i < hints.length ? hints[i] : '');

    return SizedBox(
      height: height,
      child: Column(
        children: List.generate(total * 2 - 1, (idx) {
          if (idx.isOdd) {
            return const SizedBox(height: gap);
          }
          final int i = idx ~/ 2;
          final bool unlocked = i <= hintIndex;
          final bool isCurrent = i == hintIndex;
          final double itemHeight = baseHeight * weights[i];
          final double dotHeight = (itemHeight - 4).clamp(18, 28).toDouble();
          final double dotWidth = dotHeight;
          final double fontSize = itemHeight < 34 ? 13 : 15;
          final double lineHeight = (itemHeight - 8).clamp(8, 40).toDouble();
          final double verticalPadding = (itemHeight * 0.14).clamp(2, 8).toDouble();
          return SizedBox(
            height: itemHeight,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Container(
                  width: dotWidth,
                  height: dotHeight,
                  margin: EdgeInsets.zero,
                  decoration: BoxDecoration(
                    gradient: isCurrent
                        ? const LinearGradient(
                            colors: [AppColors.primaryTeal, AppColors.primaryTealDark],
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          )
                        : unlocked
                            ? const LinearGradient(
                                colors: [AppColors.primaryTealLight, AppColors.primaryMintSoft],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              )
                            : const LinearGradient(
                                colors: [AppColors.neutralGradientStart, AppColors.neutralLine],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              ),
                    borderRadius: BorderRadius.circular(dotHeight),
                    boxShadow: isCurrent
                        ? [
                            const BoxShadow(
                              color: AppColors.primaryTealShadow,
                              blurRadius: 8,
                              offset: Offset(0, 2),
                            ),
                          ]
                        : [],
                    border: Border.all(
                      color: isCurrent
                          ? AppColors.primaryTealDark
                          : unlocked
                              ? AppColors.primaryMint
                              : AppColors.textDisabled,
                      width: isCurrent ? 2.2 : 1.2,
                    ),
                  ),
                  child: Center(
                    child: Text(
                      '${i + 1}',
                      style: AppTextStyles.hintIndex(
                        isCurrent: isCurrent,
                        unlocked: unlocked,
                        fontSize: fontSize + (itemHeight < 34 ? 1 : 2),
                        shadows: isCurrent
                            ? const [
                                Shadow(
                                  color: AppColors.black12,
                                  blurRadius: 2,
                                  offset: Offset(0, 1),
                                ),
                              ]
                            : null,
                      ),
                    ),
                  ),
                ),
                if (i != total - 1)
                  Container(
                    width: 2,
                    height: lineHeight,
                    color: unlocked ? AppColors.primaryMint : AppColors.neutralLine,
                  ),
                const SizedBox(width: 8),
                Expanded(
                  child: unlocked
                      ? AnimatedContainer(
                          duration: const Duration(milliseconds: 200),
                          curve: Curves.easeOutCubic,
                          padding: EdgeInsets.symmetric(
                            vertical: verticalPadding,
                            horizontal: 10,
                          ),
                          decoration: BoxDecoration(
                            color: isCurrent
                                ? AppColors.primaryTealLight
                                : AppColors.panelSurface,
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: isCurrent
                                  ? AppColors.primaryTealDark
                                  : AppColors.primaryMintBorder,
                              width: isCurrent ? 1.2 : 1,
                            ),
                            boxShadow: isCurrent
                                ? [
                                    const BoxShadow(
                                      color: AppColors.primaryTealShadowSoft,
                                      blurRadius: 5,
                                      offset: Offset(0, 1),
                                    ),
                                  ]
                                : [],
                          ),
                          child: Text(
                            '${hintPercents.length > i ? hintPercents[i] : ''}% · ${visibleHints[i]}',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: AppTextStyles.hintText(
                              isCurrent: isCurrent,
                              fontSize: fontSize,
                            ),
                          ),
                        )
                      : Container(),
                ),
              ],
            ),
          );
        }),
      ),
    );
  }
}
