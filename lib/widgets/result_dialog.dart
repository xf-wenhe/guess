import 'dart:math';

import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

class ResultDialog extends StatefulWidget {
  const ResultDialog(
      {super.key, required this.guess, required this.similarity});

  final String guess;
  final int similarity;

  @override
  State<ResultDialog> createState() => _ResultDialogState();
}

class _ResultDialogState extends State<ResultDialog>
    with SingleTickerProviderStateMixin {
  double _target = 0;
  late final AnimationController _glowController;
  static const Duration _delay = Duration(seconds: 1);
  static const Duration _fillDuration = Duration(milliseconds: 900);

  @override
  void initState() {
    super.initState();
    _glowController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 1),
    )..repeat(reverse: true);

    Future<void>.delayed(_delay, () {
      if (mounted) {
        setState(() {
          _target = widget.similarity / 100;
        });
      }
    });
    Future<void>.delayed(_delay + _fillDuration + const Duration(milliseconds: 400), () {
      if (mounted && Navigator.of(context).canPop()) {
        Navigator.of(context).pop();
      }
    });
  }

  @override
  void dispose() {
    _glowController.dispose();
    super.dispose();
  }

  Color _scoreColor() {
    final s = widget.similarity;
    if (s >= 95) return AppColors.scoreGold;
    if (s >= 80) return AppColors.scoreAmber;
    if (s >= 60) return AppColors.scoreGreen;
    if (s >= 30) return AppColors.neonBlue;
    return AppColors.scoreGray;
  }

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final dialogWidth = max(240.0, min(420.0, screenWidth * 0.5));
    final color = _scoreColor();

    return AnimatedBuilder(
      animation: _glowController,
      builder: (context, _) {
        final glowOpacity = 0.3 + _glowController.value * 0.3;

        return Center(
          child: Material(
            color: Colors.transparent,
            child: Container(
              width: dialogWidth,
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A2E),
                borderRadius: BorderRadius.circular(24),
                border: Border.all(
                  color: color.withOpacity(0.3),
                  width: 1,
                ),
                boxShadow: [
                  BoxShadow(
                    color: color.withOpacity(glowOpacity),
                    blurRadius: 30,
                    spreadRadius: 4,
                  ),
                ],
              ),
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // 顶部发光图标
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: RadialGradient(
                          colors: [
                            color.withOpacity(0.3),
                            color.withOpacity(0.05),
                          ],
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: color.withOpacity(0.3),
                            blurRadius: 12,
                          ),
                        ],
                      ),
                      child: Icon(Icons.bolt, color: color, size: 28),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      widget.guess,
                      style: const TextStyle(
                        fontFamily: AppFonts.primaryFamily,
                        fontSize: 18,
                        color: AppColors.textPrimary,
                        fontWeight: AppFonts.bold,
                      ),
                    ),
                    const SizedBox(height: 12),
                    // 进度条 — 霓虹风格
                    TweenAnimationBuilder<double>(
                      tween: Tween<double>(begin: 0, end: _target),
                      duration: _fillDuration,
                      curve: Curves.easeOutCubic,
                      builder: (context, value, _) {
                        return Column(
                          children: [
                            ClipRRect(
                              borderRadius: BorderRadius.circular(4),
                              child: LinearProgressIndicator(
                                value: value,
                                minHeight: 6,
                                backgroundColor:
                                    Colors.white.withOpacity(0.1),
                                valueColor: AlwaysStoppedAnimation<Color>(
                                  color,
                                ),
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              AppStrings.relationPercent(
                                  (value * 100).round()),
                              style: TextStyle(
                                fontFamily: AppFonts.primaryFamily,
                                fontSize: 13,
                                color: color,
                                fontWeight: AppFonts.bold,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              AppStrings.relationDetail(
                                AppStrings.resultAssociationLabel(
                                  (value * 100).round(),
                                ),
                              ),
                              style: const TextStyle(
                                fontFamily: AppFonts.primaryFamily,
                                fontSize: 13,
                                color: AppColors.textPrimary,
                                fontWeight: AppFonts.medium,
                              ),
                            ),
                          ],
                        );
                      },
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
