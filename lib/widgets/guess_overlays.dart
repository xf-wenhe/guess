import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show LogicalKeyboardKey;
import 'package:guess/resources/resources.dart';

import '../models/guess_models.dart';
import 'explosion.dart';
import 'star_burst.dart';

class WinOverlay extends StatelessWidget {
  const WinOverlay({
    super.key,
    required this.animation,
    required this.showResult,
    required this.onReset,
    required this.current,
    required this.winBySemantic,
    required this.lastGuess,
  });

  final Animation<double> animation;
  final bool showResult;
  final VoidCallback onReset;
  final GuessPuzzle current;
  final bool winBySemantic;
  final String lastGuess;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned.fill(
          child: GestureDetector(
            onTap: onReset,
            behavior: HitTestBehavior.opaque,
            child: Stack(
              children: [
                Container(color: AppColors.overlayBarrier),
                BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 2.8, sigmaY: 2.8),
                  child: Container(color: AppColors.transparent),
                ),
              ],
            ),
          ),
        ),
        if (!showResult)
          Center(
            child: _GifStage(
              animation: animation,
              assetPath: AppAssets.successAnimation,
              title: AppStrings.winStageTitle,
              subtitle: AppStrings.winStageSubtitle,
              accent: AppColors.success,
              fallback: StarBurst(animation: animation),
            ),
          ),
        if (showResult)
          Center(
            child: _ActionableResultCard(
              onReset: onReset,
              background: AppColors.successBg,
              border: AppColors.successBorder,
              shadow: AppColors.successShadow,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: AppColors.successChipBg,
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(color: AppColors.successBorder),
                    ),
                    child: Text(
                      AppStrings.roundSummary,
                      style: AppTextStyles.overlayChip.copyWith(
                        color: AppColors.successText,
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  const Icon(
                    Icons.verified_rounded,
                    color: AppColors.success,
                    size: 44,
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    AppStrings.hitAnswer,
                    style: AppTextStyles.overlayTitle,
                  ),
                  const SizedBox(height: 10),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppColors.successChipBg,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppColors.successBorder),
                    ),
                    child: Text(
                      AppStrings.answerIs(current.answer),
                      textAlign: TextAlign.center,
                      style: AppTextStyles.overlayAnswer,
                    ),
                  ),
                  if (winBySemantic) ...[
                    const SizedBox(height: 8),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      decoration: BoxDecoration(
                        color: AppColors.successBgSoft,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: AppColors.successChipBorder),
                      ),
                      child: Text(
                        AppStrings.semanticMatch(lastGuess),
                        style: AppTextStyles.overlaySubtitle.copyWith(
                          color: AppColors.successDeepText,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ],
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: onReset,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.primaryBlue,
                        foregroundColor: AppColors.white,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 18,
                          vertical: 13,
                        ),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      child: const Text(AppStrings.playAgain),
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class LoseOverlay extends StatelessWidget {
  const LoseOverlay({
    super.key,
    required this.animation,
    required this.showResult,
    required this.onReset,
    required this.current,
  });

  final Animation<double> animation;
  final bool showResult;
  final VoidCallback onReset;
  final GuessPuzzle current;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned.fill(
          child: GestureDetector(
            onTap: onReset,
            behavior: HitTestBehavior.opaque,
            child: Stack(
              children: [
                Container(color: AppColors.overlayBarrier),
                BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 2.8, sigmaY: 2.8),
                  child: Container(color: AppColors.transparent),
                ),
              ],
            ),
          ),
        ),
        if (!showResult)
          Center(
            child: _GifStage(
              animation: animation,
              assetPath: AppAssets.failureAnimation,
              title: AppStrings.loseStageTitle,
              subtitle: AppStrings.loseStageSubtitle,
              accent: AppColors.danger,
              fallback: Explosion(animation: animation),
            ),
          ),
        if (showResult)
          Center(
            child: _ActionableResultCard(
              onReset: onReset,
              background: AppColors.dangerBg,
              border: AppColors.dangerBorder,
              shadow: AppColors.dangerShadow,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: AppColors.dangerChipBg,
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(color: AppColors.dangerChipBorder),
                    ),
                    child: Text(
                      AppStrings.roundSummary,
                      style: AppTextStyles.overlayChip.copyWith(
                        color: AppColors.dangerText,
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  const Icon(
                    Icons.sentiment_dissatisfied,
                    color: AppColors.danger,
                    size: 44,
                  ),
                  const SizedBox(height: 10),
                  const Text(
                    AppStrings.missAnswer,
                    style: AppTextStyles.overlayTitle,
                  ),
                  const SizedBox(height: 10),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppColors.dangerBgSoft,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppColors.dangerChipBorder),
                    ),
                    child: Text(
                      AppStrings.correctAnswer(current.answer),
                      textAlign: TextAlign.center,
                      style: AppTextStyles.overlayAnswer,
                    ),
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: onReset,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.primaryBlue,
                        foregroundColor: AppColors.white,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 18,
                          vertical: 13,
                        ),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      child: const Text(AppStrings.retry),
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class _ActionableResultCard extends StatelessWidget {
  const _ActionableResultCard({
    required this.onReset,
    required this.child,
    this.background = AppColors.neutralSurface,
    this.border = AppColors.neutralBorder,
    this.shadow = AppColors.primaryBlueShadow,
  });

  final VoidCallback onReset;
  final Widget child;
  final Color background;
  final Color border;
  final Color shadow;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    final cardWidth = width < 400 ? width - 32 : 340.0;
    return Shortcuts(
      shortcuts: {
        LogicalKeySet(LogicalKeyboardKey.enter): const ActivateIntent(),
        LogicalKeySet(LogicalKeyboardKey.numpadEnter): const ActivateIntent(),
      },
      child: Actions(
        actions: {
          ActivateIntent: CallbackAction<ActivateIntent>(
            onInvoke: (_) {
              onReset();
              return null;
            },
          ),
        },
        child: Focus(
          autofocus: true,
          child: AnimatedScale(
            scale: 1,
            duration: const Duration(milliseconds: 220),
            child: Container(
              width: cardWidth,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: background,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: border),
                boxShadow: [
                  BoxShadow(color: shadow, blurRadius: 18, offset: const Offset(0, 8)),
                ],
              ),
              child: child,
            ),
          ),
        ),
      ),
    );
  }
}

class _GifStage extends StatelessWidget {
  const _GifStage({
    required this.animation,
    required this.assetPath,
    required this.title,
    required this.subtitle,
    required this.accent,
    required this.fallback,
  });

  final Animation<double> animation;
  final String assetPath;
  final String title;
  final String subtitle;
  final Color accent;
  final Widget fallback;

  @override
  Widget build(BuildContext context) {
    final screen = MediaQuery.of(context).size;
    final stageWidth = screen.width < 540 ? screen.width - 30 : 510.0;
    final stageHeight = screen.height < 760 ? 240.0 : 300.0;
    return IgnorePointer(
      child: AnimatedBuilder(
        animation: animation,
        builder: (context, _) {
          return Opacity(
            opacity: animation.value,
            child: Center(
              child: Container(
                width: stageWidth,
                height: stageHeight,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(32),
                  boxShadow: [
                    BoxShadow(
                      color: accent.withOpacity(0.18),
                      blurRadius: 36,
                      offset: const Offset(0, 14),
                    ),
                  ],
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [AppColors.white, accent.withOpacity(0.08)],
                  ),
                ),
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(32),
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              AppColors.white.withOpacity(0.85),
                              AppColors.transparent,
                              accent.withOpacity(0.10),
                            ],
                            stops: const [0.0, 0.7, 1.0],
                          ),
                        ),
                      ),
                    ),
                    Center(
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(22),
                        child: Image.asset(
                          assetPath,
                          fit: BoxFit.cover,
                          width: stageWidth - 48,
                          height: stageHeight - 90,
                          errorBuilder: (_, __, ___) {
                            return SizedBox(
                              width: stageWidth - 48,
                              height: stageHeight - 90,
                              child: Stack(
                                children: [
                                  Positioned.fill(
                                    child: Opacity(
                                      opacity: 0.85,
                                      child: fallback,
                                    ),
                                  ),
                                  Center(
                                    child: Icon(
                                      Icons.movie_filter_outlined,
                                      size: 30,
                                      color: accent.withOpacity(0.8),
                                    ),
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                      ),
                    ),
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom: 0,
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              title,
                              style: AppTextStyles.stageTitle(accent),
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 7),
                            Text(
                              subtitle,
                              style: AppTextStyles.stageSubtitle,
                              textAlign: TextAlign.center,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
