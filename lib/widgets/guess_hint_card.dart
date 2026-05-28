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
    final List<String> visibleHints =
        List.generate(total, (i) => i < hints.length ? hints[i] : '');

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
          final double fontSize = itemHeight < 34 ? 13 : 15;
          final double lineHeight =
              (itemHeight - 8).clamp(8, 40).toDouble();
          final double verticalPadding =
              (itemHeight * 0.14).clamp(2, 8).toDouble();

          // 当前激活 = 霓虹琥珀发光, 已解锁 = 青绿, 未解锁 = 灰色

          return SizedBox(
            height: itemHeight,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                // 编号圆点
                Container(
                  width: dotHeight,
                  height: dotHeight,
                  margin: EdgeInsets.zero,
                  decoration: BoxDecoration(
                    gradient: isCurrent
                        ? LinearGradient(
                            colors: [
                              AppColors.neonAmber,
                              AppColors.neonOrange,
                            ],
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          )
                        : unlocked
                            ? LinearGradient(
                                colors: [
                                  AppColors.neonGreen.withOpacity(0.6),
                                  AppColors.neonGreen.withOpacity(0.3),
                                ],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              )
                            : LinearGradient(
                                colors: [
                                  AppColors.neutralGradientStart,
                                  AppColors.neutralLine,
                                ],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              ),
                    borderRadius: BorderRadius.circular(dotHeight),
                    boxShadow: isCurrent
                        ? [
                            BoxShadow(
                              color: AppColors.neonAmber.withOpacity(0.5),
                              blurRadius: 10,
                              spreadRadius: 1,
                            ),
                          ]
                        : unlocked
                            ? [
                                BoxShadow(
                                  color: AppColors.neonGreen.withOpacity(0.15),
                                  blurRadius: 4,
                                ),
                              ]
                            : [],
                    border: Border.all(
                      color: isCurrent
                          ? AppColors.neonAmber
                          : unlocked
                              ? AppColors.neonGreen.withOpacity(0.4)
                              : AppColors.textDisabled,
                      width: isCurrent ? 2 : 1,
                    ),
                  ),
                  child: Center(
                    child: Text(
                      '${i + 1}',
                      style: TextStyle(
                        fontFamily: AppFonts.primaryFamily,
                        color: isCurrent
                            ? const Color(0xFF1A1A2E)
                            : unlocked
                                ? AppColors.neonGreen
                                : AppColors.textStatusLight,
                        fontWeight: AppFonts.black,
                        fontSize: fontSize + 1,
                        letterSpacing: 0.2,
                        shadows: isCurrent
                            ? [
                                Shadow(
                                  color: AppColors.neonAmber.withOpacity(0.3),
                                  blurRadius: 4,
                                ),
                              ]
                            : null,
                      ),
                    ),
                  ),
                ),
                // 连接线
                if (i != total - 1)
                  Container(
                    width: 2,
                    height: lineHeight,
                    decoration: BoxDecoration(
                      gradient: unlocked
                          ? LinearGradient(
                              colors: [
                                AppColors.neonGreen.withOpacity(0.3),
                                AppColors.neonGreen.withOpacity(0.1),
                              ],
                            )
                          : null,
                      color: unlocked ? null : AppColors.neutralLine,
                    ),
                  ),
                const SizedBox(width: 8),
                // 提示文字
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
                                ? AppColors.neonAmber.withOpacity(0.1)
                                : AppColors.panelSurface,
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: isCurrent
                                  ? AppColors.neonAmber.withOpacity(0.3)
                                  : AppColors.neonGreen.withOpacity(0.15),
                              width: isCurrent ? 1.2 : 1,
                            ),
                            boxShadow: isCurrent
                                ? [
                                    BoxShadow(
                                      color:
                                          AppColors.neonAmber.withOpacity(0.08),
                                      blurRadius: 6,
                                      offset: const Offset(0, 1),
                                    ),
                                  ]
                                : [],
                          ),
                          child: Text(
                            '${hintPercents.length > i ? hintPercents[i] : ''}% · ${visibleHints[i]}',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontFamily: AppFonts.primaryFamily,
                              fontSize: fontSize,
                              fontWeight: isCurrent
                                  ? AppFonts.bold
                                  : AppFonts.medium,
                              color: isCurrent
                                  ? AppColors.neonAmber
                                  : AppColors.textSecondary,
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
