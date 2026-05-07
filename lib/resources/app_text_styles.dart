import 'package:flutter/material.dart';

import 'app_colors.dart';
import 'app_fonts.dart';

class AppTextStyles {
  const AppTextStyles._();

  static const appBarTitle = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 20,
    fontWeight: AppFonts.extraBold,
    color: AppColors.appBarForeground,
    letterSpacing: 0.4,
  );

  static const snackBarContent = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    color: AppColors.white,
  );

  static const buttonLabel = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontWeight: AppFonts.bold,
  );

  static const panelTitle = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 15,
    fontWeight: AppFonts.bold,
    color: AppColors.textPrimary,
  );

  static const statusTip = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    color: AppColors.primaryTealDark,
    fontSize: 12,
    fontWeight: AppFonts.bold,
  );

  static const statusSectionLabel = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    color: AppColors.textStatusLight,
    fontSize: 10.5,
  );

  static const statusUnit = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    color: AppColors.white,
    fontSize: 15,
    fontWeight: AppFonts.bold,
  );

  static const statusCaption = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    color: AppColors.textStatusLight,
    fontSize: 10,
    fontWeight: AppFonts.semibold,
  );

  static const statusPrompt = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    color: AppColors.white,
    fontSize: 10.5,
    fontWeight: AppFonts.medium,
  );

  static const infoPill = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    color: AppColors.white,
    fontSize: 10.5,
    fontWeight: AppFonts.bold,
  );

  static const overlayChip = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 12,
    fontWeight: AppFonts.bold,
  );

  static const overlayTitle = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 20,
    fontWeight: AppFonts.bold,
  );

  static const overlayAnswer = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 17,
    color: AppColors.textStrong,
    fontWeight: AppFonts.bold,
  );

  static const overlaySubtitle = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 14,
    fontWeight: AppFonts.medium,
  );

  static const stageSubtitle = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 15,
    color: AppColors.textSecondary,
    fontWeight: AppFonts.medium,
  );

  static TextStyle stageTitle(Color accent) {
    return TextStyle(
      fontFamily: AppFonts.primaryFamily,
      fontSize: 22,
      fontWeight: AppFonts.bold,
      foreground: Paint()
        ..shader = LinearGradient(
          colors: [accent, accent.withOpacity(0.7)],
        ).createShader(const Rect.fromLTWH(0, 0, 200, 30)),
      shadows: [
        Shadow(
          color: accent.withOpacity(0.18),
          blurRadius: 8,
          offset: const Offset(0, 2),
        ),
      ],
    );
  }

  static const dialogGuess = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 16,
    fontWeight: AppFonts.semibold,
  );

  static const dialogValue = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 12,
    color: AppColors.primaryBlueDark,
    fontWeight: AppFonts.semibold,
  );

  static const dialogCaption = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 11,
    color: AppColors.black54,
  );

  static const settingsTitle = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 16,
    fontWeight: AppFonts.semibold,
  );

  static const settingsCaption = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 12,
    color: AppColors.black54,
  );

  static TextStyle statusHeadline(TextStyle? base) {
    return (base ?? const TextStyle()).copyWith(
      fontFamily: AppFonts.primaryFamily,
      fontSize: 26,
      height: 0.95,
      color: AppColors.white,
      fontWeight: AppFonts.extraBold,
    );
  }

  static TextStyle hintIndex({
    required bool isCurrent,
    required bool unlocked,
    required double fontSize,
    List<Shadow>? shadows,
  }) {
    return TextStyle(
      fontFamily: AppFonts.primaryFamily,
      color: isCurrent
          ? AppColors.white
          : unlocked
              ? AppColors.primaryTealDark
              : AppColors.textMuted,
      fontWeight: AppFonts.black,
      fontSize: fontSize,
      letterSpacing: 0.2,
      shadows: shadows,
    );
  }

  static TextStyle hintText({
    required bool isCurrent,
    required double fontSize,
  }) {
    return TextStyle(
      fontFamily: AppFonts.primaryFamily,
      fontSize: fontSize,
      fontWeight: isCurrent ? AppFonts.bold : AppFonts.medium,
      color: isCurrent ? AppColors.primaryTealDark : AppColors.textSecondary,
    );
  }

  static TextStyle notice(Color color) {
    return TextStyle(
      fontFamily: AppFonts.primaryFamily,
      fontSize: 11.5,
      color: color,
      fontWeight: AppFonts.semibold,
    );
  }

  static TextStyle historyBadge(double fontSize) {
    return TextStyle(
      fontFamily: AppFonts.primaryFamily,
      fontSize: fontSize,
      color: AppColors.primaryBlueText,
      fontWeight: AppFonts.extraBold,
    );
  }

  static TextStyle historyWord({required bool hasData, required double fontSize}) {
    return TextStyle(
      fontFamily: AppFonts.primaryFamily,
      fontSize: fontSize,
      color: hasData ? AppColors.textPrimary : AppColors.textMuted,
      fontWeight: AppFonts.bold,
    );
  }

  static TextStyle historyScore(double fontSize) {
    return TextStyle(
      fontFamily: AppFonts.primaryFamily,
      fontSize: fontSize,
      color: AppColors.primaryBlueDeep,
      fontWeight: AppFonts.extraBold,
      height: 1.0,
    );
  }

  static TextStyle historyAssociation(double fontSize) {
    return TextStyle(
      fontFamily: AppFonts.primaryFamily,
      fontSize: fontSize,
      color: AppColors.primaryBlueTextSoft,
      fontWeight: AppFonts.semibold,
      height: 1.0,
    );
  }

  static TextStyle waiting(double fontSize) {
    return TextStyle(
      fontFamily: AppFonts.primaryFamily,
      fontSize: fontSize,
      color: AppColors.textMuted,
      fontWeight: AppFonts.semibold,
    );
  }

  static const historyMetaChip = TextStyle(
    fontFamily: AppFonts.primaryFamily,
    fontSize: 14,
    color: AppColors.primaryBlueText,
    fontWeight: AppFonts.bold,
  );
}