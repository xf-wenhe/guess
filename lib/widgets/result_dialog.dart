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

class _ResultDialogState extends State<ResultDialog> {
  double _target = 0;
  static const Duration _delay = Duration(seconds: 1);
  static const Duration _fillDuration = Duration(milliseconds: 900);

  @override
  void initState() {
    super.initState();
    Future<void>.delayed(_delay, () {
      if (mounted) {
        setState(() {
          _target = widget.similarity / 100;
        });
      }
    });
    Future<void>.delayed(_delay + _fillDuration, () {
      if (mounted && Navigator.of(context).canPop()) {
        Navigator.of(context).pop();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final dialogWidth = max(220.0, min(420.0, screenWidth * 0.5));
    return Center(
      child: Material(
        color: AppColors.white,
        borderRadius: BorderRadius.circular(16),
        child: SizedBox(
          width: dialogWidth,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.bolt, color: AppColors.primaryBlueDark, size: 24),
                const SizedBox(height: 6),
                Text(
                  widget.guess,
                  style: AppTextStyles.dialogGuess,
                ),
                const SizedBox(height: 10),
                TweenAnimationBuilder<double>(
                  tween: Tween<double>(begin: 0, end: _target),
                  duration: _fillDuration,
                  curve: Curves.easeOutCubic,
                  builder: (context, value, _) {
                    return Column(
                      children: [
                        LinearProgressIndicator(
                          value: value,
                          minHeight: 6,
                          backgroundColor: AppColors.primaryBlueBadgeBorder,
                          valueColor: const AlwaysStoppedAnimation<Color>(
                            AppColors.primaryBlueDark,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          AppStrings.relationPercent((value * 100).round()),
                          style: AppTextStyles.dialogValue,
                        ),
                        const SizedBox(height: 2),
                        Text(
                          AppStrings.relationDetail(
                            AppStrings.resultAssociationLabel(
                              (value * 100).round(),
                            ),
                          ),
                          style: AppTextStyles.dialogCaption,
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
  }
}
