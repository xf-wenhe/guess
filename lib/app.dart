import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'resources/resources.dart';
import 'screens/guess_home_page.dart';

class GuessApp extends StatelessWidget {
  const GuessApp({super.key, this.autoStartLocalEmbedding = true});

  final bool autoStartLocalEmbedding;

  @override
  Widget build(BuildContext context) {
    final colorScheme = ColorScheme.fromSeed(seedColor: AppColors.seed);
    final baseTheme = ThemeData(
      fontFamily: GoogleFonts.notoSansSc().fontFamily,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: AppColors.scaffoldBackground,
      useMaterial3: true,
    );
    final appBarTitleStyle = baseTheme.textTheme.titleLarge?.copyWith(
          fontFamily: AppFonts.primaryFamily,
          fontSize: AppTextStyles.appBarTitle.fontSize,
          fontWeight: AppTextStyles.appBarTitle.fontWeight,
          color: AppTextStyles.appBarTitle.color,
          letterSpacing: AppTextStyles.appBarTitle.letterSpacing,
        ) ??
        AppTextStyles.appBarTitle;

    return MaterialApp(
      title: AppStrings.appMaterialTitle,
      debugShowCheckedModeBanner: false,
      themeAnimationDuration: Duration.zero,
      theme: baseTheme.copyWith(
        appBarTheme: const AppBarTheme(
          backgroundColor: AppColors.transparent,
          foregroundColor: AppColors.appBarForeground,
          elevation: 0,
          scrolledUnderElevation: 0,
          centerTitle: true,
        ).copyWith(titleTextStyle: appBarTitleStyle),
        cardTheme: CardTheme(
          color: AppColors.cardBackground,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(18),
            side: const BorderSide(color: AppColors.cardBorder, width: 1),
          ),
        ),
        snackBarTheme: SnackBarThemeData(
          behavior: SnackBarBehavior.floating,
          backgroundColor: AppColors.snackBarBackground,
          contentTextStyle: AppTextStyles.snackBarContent,
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.primaryTealDark,
            foregroundColor: AppColors.white,
            textStyle: AppTextStyles.buttonLabel,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
      ),
      home: GuessHomePage(autoStartLocalEmbedding: autoStartLocalEmbedding),
    );
  }
}
