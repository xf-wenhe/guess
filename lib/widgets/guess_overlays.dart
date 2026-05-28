import 'dart:math';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

import '../models/guess_models.dart';
import 'explosion.dart';
import 'star_burst.dart';

// ============================================================
// WinOverlay — 胜利庆典覆盖层
// ============================================================
class WinOverlay extends StatefulWidget {
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
  State<WinOverlay> createState() => _WinOverlayState();
}

class _WinOverlayState extends State<WinOverlay>
  with TickerProviderStateMixin {
  late final AnimationController _glowController;
  late final AnimationController _bounceController;

  @override
  void initState() {
    super.initState();
    _glowController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _bounceController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );

    // 结果卡片出现时触发弹跳动画
    widget.animation.addListener(_checkShowResult);
  }

  void _checkShowResult() {
    if (widget.showResult && _bounceController.isDismissed) {
      _bounceController.forward();
    }
  }

  @override
  void dispose() {
    _bounceController.dispose();
    _glowController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _glowController,
      builder: (context, _) {
        final glowOpacity = 0.3 + _glowController.value * 0.3;

        return Stack(
          children: [
            // ---- 遮罩层 ----
            Positioned.fill(
              child: GestureDetector(
                onTap: widget.onReset,
                behavior: HitTestBehavior.opaque,
                child: Stack(
                  children: [
                    Container(
                      decoration: BoxDecoration(
                        gradient: RadialGradient(
                          colors: [
                            AppColors.neonGreen.withOpacity(0.08),
                            AppColors.overlayBarrier,
                          ],
                          center: Alignment.center,
                          radius: 1.5,
                        ),
                      ),
                    ),
                    BackdropFilter(
                      filter: ImageFilter.blur(sigmaX: 4, sigmaY: 4),
                      child: Container(color: Colors.transparent),
                    ),
                  ],
                ),
              ),
            ),

            // ---- 阶段1：庆典动画 ----
            if (!widget.showResult)
              Center(
                child: _GifStage(
                  animation: widget.animation,
                  assetPath: AppAssets.successAnimation,
                  title: AppStrings.winStageTitle,
                  subtitle: AppStrings.winStageSubtitle,
                  accent: AppColors.neonGreen,
                  fallback: StarBurst(animation: widget.animation),
                ),
              ),

            // ---- 阶段2：结果卡片 (带弹跳动画) ----
            if (widget.showResult)
              Center(
                child: AnimatedBuilder(
                  animation: _bounceController,
                  builder: (context, _) {
                    // 弹性曲线：先放大再回弹
                    final scale = _bounceT(_bounceController.value);
                    return Transform.scale(
                      scale: scale,
                      child: _buildWinCard(glowOpacity),
                    );
                  },
                ),
              ),
          ],
        );
      },
    );
  }

  /// 弹跳曲线：0→1.08→0.94→1.00
  double _bounceT(double t) {
    if (t < 0.3) return 0.7 + 0.38 * (t / 0.3);
    if (t < 0.6) return 1.08 - 0.14 * ((t - 0.3) / 0.3);
    return 0.94 + 0.06 * ((t - 0.6) / 0.4);
  }

  Widget _buildWinCard(double glowOpacity) {
    return Container(
      width: 340,
      constraints: BoxConstraints(
        maxWidth: MediaQuery.of(context).size.width - 32,
      ),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF0A2A1A),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: AppColors.neonGreen.withOpacity(glowOpacity),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.neonGreen.withOpacity(glowOpacity * 0.6),
            blurRadius: 30,
            spreadRadius: 4,
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 标签
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: AppColors.neonGreen.withOpacity(0.15),
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: AppColors.neonGreen.withOpacity(0.3)),
            ),
            child: const Text(
              AppStrings.roundSummary,
              style: TextStyle(
                fontFamily: AppFonts.primaryFamily,
                fontSize: 12,
                color: AppColors.neonGreen,
                fontWeight: AppFonts.bold,
              ),
            ),
          ),
          const SizedBox(height: 14),
          // 图标
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  AppColors.neonGreen.withOpacity(0.3),
                  AppColors.neonGreen.withOpacity(0.05),
                ],
              ),
              boxShadow: [
                BoxShadow(
                  color: AppColors.neonGreen.withOpacity(glowOpacity),
                  blurRadius: 20,
                ),
              ],
            ),
            child: const Icon(
              Icons.emoji_events_rounded,
              color: AppColors.neonGreen,
              size: 36,
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            AppStrings.hitAnswer,
            style: TextStyle(
              fontFamily: AppFonts.primaryFamily,
              fontSize: 22,
              color: Colors.white,
              fontWeight: AppFonts.bold,
            ),
          ),
          const SizedBox(height: 14),
          // 答案卡片
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  AppColors.neonGreen.withOpacity(0.15),
                  AppColors.neonGreen.withOpacity(0.05),
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                color: AppColors.neonGreen.withOpacity(0.25),
              ),
            ),
            child: Text(
              AppStrings.answerIs(widget.current.answer),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: AppFonts.primaryFamily,
                fontSize: 22,
                color: AppColors.neonGreen,
                fontWeight: AppFonts.extraBold,
                letterSpacing: 1.5,
                shadows: [
                  Shadow(
                    color: AppColors.neonGreen.withOpacity(0.6),
                    blurRadius: 12,
                  ),
                ],
              ),
            ),
          ),
          if (widget.winBySemantic) ...[
            const SizedBox(height: 10),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.06),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white.withOpacity(0.1)),
              ),
              child: Text(
                AppStrings.semanticMatch(widget.lastGuess),
                style: const TextStyle(
                  fontFamily: AppFonts.primaryFamily,
                  fontSize: 14,
                  color: AppColors.textPrimary,
                ),
                textAlign: TextAlign.center,
              ),
            ),
          ],
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: widget.onReset,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.neonGreen,
                foregroundColor: const Color(0xFF0A2A1A),
                padding: const EdgeInsets.symmetric(
                  horizontal: 24,
                  vertical: 14,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
                textStyle: const TextStyle(
                  fontFamily: AppFonts.primaryFamily,
                  fontSize: 16,
                  fontWeight: AppFonts.bold,
                ),
              ),
              child: const Text(AppStrings.playAgain),
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================
// LoseOverlay — 失败炸弹爆炸覆盖层
// ============================================================
class LoseOverlay extends StatefulWidget {
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
  State<LoseOverlay> createState() => _LoseOverlayState();
}

class _LoseOverlayState extends State<LoseOverlay>
  with TickerProviderStateMixin {
  late final AnimationController _glowController;
  late final AnimationController _shakeController;

  @override
  void initState() {
    super.initState();
    _glowController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _shakeController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );

    widget.animation.addListener(_checkShowResult);
  }

  void _checkShowResult() {
    if (widget.showResult && _shakeController.isDismissed) {
      _shakeController.forward();
    }
  }

  @override
  void dispose() {
    _shakeController.dispose();
    _glowController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _glowController,
      builder: (context, _) {
        final glowOpacity = 0.3 + _glowController.value * 0.3;

        // ---- 屏幕震动 ----
        return AnimatedBuilder(
          animation: _shakeController,
          builder: (context, _) {
            final shakeOffset = _shakeOffsetValue(_shakeController.value);
            return Transform.translate(
              offset: shakeOffset,
              child: Stack(
                children: [
                  // ---- 遮罩层 ----
                  Positioned.fill(
                    child: GestureDetector(
                      onTap: widget.onReset,
                      behavior: HitTestBehavior.opaque,
                      child: Stack(
                        children: [
                          Container(
                            decoration: BoxDecoration(
                              gradient: RadialGradient(
                                colors: [
                                  AppColors.neonPink.withOpacity(0.06),
                                  AppColors.overlayBarrier,
                                ],
                                center: Alignment.center,
                                radius: 1.5,
                              ),
                            ),
                          ),
                          BackdropFilter(
                            filter: ImageFilter.blur(sigmaX: 4, sigmaY: 4),
                            child: Container(color: Colors.transparent),
                          ),
                        ],
                      ),
                    ),
                  ),

                  // ---- 阶段1：炸弹爆炸动画 ----
                  if (!widget.showResult)
                    Center(
                      child: _GifStage(
                        animation: widget.animation,
                        assetPath: AppAssets.failureAnimation,
                        title: AppStrings.loseStageTitle,
                        subtitle: AppStrings.loseStageSubtitle,
                        accent: AppColors.neonPink,
                        fallback: Explosion(animation: widget.animation),
                      ),
                    ),

                  // ---- 阶段2：结果卡片 ----
                  if (widget.showResult)
                    Center(
                      child: _buildLoseCard(glowOpacity),
                    ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  /// 震动偏移：剧烈震动然后衰减
  Offset _shakeOffsetValue(double t) {
    if (t <= 0 || t >= 1) return Offset.zero;
    final intensity = (1.0 - t).clamp(0.0, 1.0); // 震动强度逐渐衰减
    const freq = 18; // 震动频率
    final dx = sin(t * freq * pi * 2) * 12 * intensity;
    final dy = cos(t * freq * pi * 2.3) * 8 * intensity;
    return Offset(dx, dy);
  }

  Widget _buildLoseCard(double glowOpacity) {
    return Container(
      width: 340,
      constraints: BoxConstraints(
        maxWidth: MediaQuery.of(context).size.width - 32,
      ),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF2A0A0A),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: AppColors.neonOrange.withOpacity(glowOpacity),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.neonOrange.withOpacity(glowOpacity * 0.6),
            blurRadius: 30,
            spreadRadius: 4,
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 标签
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: AppColors.neonOrange.withOpacity(0.15),
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: AppColors.neonOrange.withOpacity(0.3)),
            ),
            child: const Text(
              AppStrings.roundSummary,
              style: TextStyle(
                fontFamily: AppFonts.primaryFamily,
                fontSize: 12,
                color: AppColors.neonOrange,
                fontWeight: AppFonts.bold,
              ),
            ),
          ),
          const SizedBox(height: 14),
          // 图标
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  AppColors.neonOrange.withOpacity(0.3),
                  AppColors.neonOrange.withOpacity(0.05),
                ],
              ),
              boxShadow: [
                BoxShadow(
                  color: AppColors.neonOrange.withOpacity(glowOpacity),
                  blurRadius: 20,
                ),
              ],
            ),
            child: const Icon(
              Icons.local_fire_department_rounded,
              color: AppColors.neonOrange,
              size: 36,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            AppStrings.missAnswer,
            style: TextStyle(
              fontFamily: AppFonts.primaryFamily,
              fontSize: 22,
              color: Colors.white,
              fontWeight: AppFonts.bold,
              shadows: [
                Shadow(
                  color: AppColors.neonOrange.withOpacity(0.5),
                  blurRadius: 8,
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          // 答案卡片 — 火焰色调
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  AppColors.neonOrange.withOpacity(0.15),
                  AppColors.neonPink.withOpacity(0.08),
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                color: AppColors.neonOrange.withOpacity(0.25),
              ),
            ),
            child: Text(
              AppStrings.correctAnswer(widget.current.answer),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: AppFonts.primaryFamily,
                fontSize: 22,
                color: AppColors.neonOrange,
                fontWeight: AppFonts.extraBold,
                letterSpacing: 1.5,
                shadows: [
                  Shadow(
                    color: AppColors.neonOrange.withOpacity(0.5),
                    blurRadius: 12,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: widget.onReset,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.neonOrange,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(
                  horizontal: 24,
                  vertical: 14,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
                textStyle: const TextStyle(
                  fontFamily: AppFonts.primaryFamily,
                  fontSize: 16,
                  fontWeight: AppFonts.bold,
                ),
              ),
              child: const Text(AppStrings.retry),
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================
// _GifStage — 动画阶段展示组件
// ============================================================
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
    final stageHeight = screen.height < 760 ? 280.0 : 340.0;
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
                      color: accent.withOpacity(0.2),
                      blurRadius: 40,
                      offset: const Offset(0, 14),
                    ),
                  ],
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      const Color(0xFF1A1A2E),
                      accent.withOpacity(0.08),
                    ],
                  ),
                ),
                child: Stack(
                  children: [
                    // 背景渐变
                    Positioned.fill(
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(32),
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              Colors.white.withOpacity(0.05),
                              Colors.transparent,
                              accent.withOpacity(0.1),
                            ],
                            stops: const [0.0, 0.7, 1.0],
                          ),
                        ),
                      ),
                    ),
                    // 动效区域
                    Center(
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(22),
                        child: Image.asset(
                          assetPath,
                          fit: BoxFit.cover,
                          width: stageWidth - 48,
                          height: stageHeight - 100,
                          errorBuilder: (_, __, ___) {
                            return SizedBox(
                              width: stageWidth - 48,
                              height: stageHeight - 100,
                              child: fallback,
                            );
                          },
                        ),
                      ),
                    ),
                    // 底部文字
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom: 0,
                      child: Padding(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 18, vertical: 18),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              title,
                              style: TextStyle(
                                fontFamily: AppFonts.primaryFamily,
                                fontSize: 22,
                                fontWeight: AppFonts.bold,
                                color: accent,
                                shadows: [
                                  Shadow(
                                    color: accent.withOpacity(0.4),
                                    blurRadius: 12,
                                  ),
                                ],
                              ),
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 7),
                            Text(
                              subtitle,
                              style: const TextStyle(
                                fontFamily: AppFonts.primaryFamily,
                                fontSize: 15,
                                color: AppColors.textPrimary,
                                fontWeight: AppFonts.medium,
                              ),
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
