import 'package:flutter/material.dart';

class AppColors {
  const AppColors._();

  static const transparent = Colors.transparent;
  static const white = Colors.white;
  static const black12 = Colors.black12;
  static const black54 = Colors.black54;

  // ===== 暗色主题基础色 =====
  static const seed = Color(0xFF0EA5A6);
  static const scaffoldBackground = Color(0xFF0A0E21);
  static const appBarForeground = Color(0xFFE2E8F0);
  static const cardBackground = Color(0x1AFFFFFF); // 半透明玻璃态
  static const cardBorder = Color(0x20FFFFFF);      // 玻璃态边框
  static const snackBarBackground = Color(0xFF1A1F3A);

  // ===== 玻璃态面板专用色 =====
  static const glassPanelBg = Color(0x12FFFFFF);
  static const glassPanelBorder = Color(0x18FFFFFF);
  static const glassPanelHighlight = Color(0x08FFFFFF);

  static const primaryTeal = Color(0xFF14B8A6);
  static const primaryTealDark = Color(0xFF0F766E);
  static const primaryTealSoft = Color(0xFFE8F6F2);
  static const primaryTealBorder = Color(0xFFB6E7DA);
  static const primaryTealLight = Color(0xFFE0F7FA);
  static const primaryTealShadow = Color(0x3300B894);
  static const primaryTealShadowSoft = Color(0x2200B894);
  static const primaryMint = Color(0xFF5EEAD4);
  static const primaryMintSoft = Color(0xFFCCFBF1);
  static const primaryMintBorder = Color(0xFFD1FAE5);

  static const primaryBlue = Color(0xFF2563EB);
  static const primaryBlueBright = Color(0xFF3B82F6);
  static const primaryBlueDark = Color(0xFF145DFF);
  static const primaryBlueDeep = Color(0xFF1D4ED8);
  static const primaryBlueText = Color(0xFF1E3A8A);
  static const primaryBlueSoft = Color(0xFFF1F5FF);
  static const primaryBlueBorder = Color(0xFFD3DDF9);
  static const primaryBlueNotice = Color(0x1A3B82F6);
  static const primaryBlueNoticeBorder = Color(0x303B82F6);
  static const primaryBlueNoticeText = Color(0xFF93C5FD);
  static const primaryBlueShadow = Color(0x332563EB);
  static const primaryBlueTextSoft = Color(0xFF5C77C7);
  static const primaryBlueBadge = Color(0xFFE8F1FF);
  static const primaryBlueBadgeBorder = Color(0xFFE3E8EF);

  static const success = Color(0xFF16A34A);
  static const successText = Color(0xFF15803D);
  static const successDeepText = Color(0xFF166534);
  static const successBg = Color(0xFFF7FFF9);
  static const successBorder = Color(0xFFBBF7D0);
  static const successShadow = Color(0x3316A34A);
  static const successChipBg = Color(0xFFECFDF3);
  static const successChipBorder = Color(0xFFDCFCE7);
  static const successBgSoft = Color(0xFFF0FDF4);

  static const danger = Color(0xFFEF4444);
  static const dangerText = Color(0xFFFCA5A5);
  static const dangerBg = Color(0xFFFFFAFA);
  static const dangerBorder = Color(0xFFF6D6D6);
  static const dangerShadow = Color(0x33291E1E);
  static const dangerChipBg = Color(0xFFFFEFEF);
  static const dangerChipBorder = Color(0xFFFECACA);
  static const dangerBgSoft = Color(0xFFFFF2F2);
  static const dangerNoticeBg = Color(0x1ADC2626);
  static const dangerNoticeBorder = Color(0x30DC2626);

  static const warningBg = Color(0x1AF59E0B);
  static const warningBorder = Color(0x30F59E0B);
  static const warningText = Color(0xFFFBBF24);

  static const textPrimary = Color(0xFFF1F5F9);
  static const textSecondary = Color(0xFF94A3B8);
  static const textMuted = Color(0xFF64748B);
  static const textStrong = Color(0xFFF8FAFC);
  static const textStatusLight = Color(0xFFCBD5E1);
  static const textDisabled = Color(0xFF475569);

  static const inputBackground = Color(0x15FFFFFF);
  static const inputBorder = Color(0x20FFFFFF);
  static const inputFill = Color(0x0DFFFFFF);
  static const inputOutline = Color(0x1AFFFFFF);
  static const sheetInputFill = Color(0x0DFFFFFF);

  static const historyRow = Color(0x08FFFFFF);
  static const historyRowEmpty = Color(0x04FFFFFF);
  static const historyRowBorder = Color(0x10FFFFFF);

  static const overlayBarrier = Color(0x80121A2B);
  static const panelSurface = Color(0x0AFFFFFF);
  static const neutralSurface = Color(0x0AFFFFFF);
  static const neutralBorder = Color(0x1AFFFFFF);
  static const neutralLine = Color(0x15FFFFFF);
  static const neutralGradientStart = Color(0x08FFFFFF);

  static const decorMint = Color(0x1514B8A6);
  static const decorIvory = Color(0x0AFFFFFF);
  static const decorWarm = Color(0x15F59E0B);
  static const decorAmber = Color(0xFFF59E0B);

  static const explosionPalette = <Color>[
    Color(0xFFFF3B30),
    Color(0xFFFF8A00),
    Color(0xFFFFD166),
    Color(0xFFFF6B6B),
    Color(0xFFFFC857),
  ];

  static const starBurstPalette = <Color>[
    Color(0xFFFFD54F),
    Color(0xFFFFF59D),
    Color(0xFFFFC107),
    Color(0xFFFFE082),
  ];

  // ===== 霓虹发光色 =====
  static const neonPurple = Color(0xFFA855F7);
  static const neonPink = Color(0xFFEC4899);
  static const neonCyan = Color(0xFF22D3EE);
  static const neonBlue = Color(0xFF60A5FA);
  static const neonGreen = Color(0xFF4ADE80);
  static const neonAmber = Color(0xFFFBBF24);
  static const neonOrange = Color(0xFFFB923C);

  // ===== 分数热力色 (暗色主题) =====
  static const scoreGray = Color(0xFF64748B);    // 0–29%
  static const scoreGreen = Color(0xFF4ADE80);   // 60–79%
  static const scoreAmber = Color(0xFFFBBF24);   // 80–94%
  static const scoreGold = Color(0xFFFB923C);    // 95–100%

  // 分数发光色 (用于阴影和光晕)
  static const scoreGrayGlow = Color(0x4064748B);
  static const scoreGreenGlow = Color(0x404ADE80);
  static const scoreAmberGlow = Color(0x40FBBF24);
  static const scoreGoldGlow = Color(0x40FB923C);

  // 分数背景色 (暗色)
  static const scoreGrayBg = Color(0x1A64748B);
  static const scoreGreenBg = Color(0x1A4ADE80);
  static const scoreAmberBg = Color(0x1AFBBF24);
  static const scoreGoldBg = Color(0x1AFB923C);

  // 用户界面相关
  static const primary = Color(0xFF14B8A6);
  static const successGreen = Color(0xFF22C55E);
  static const error = Color(0xFFEF4444);
  static const errorLight = Color(0xFFFFA0A0);
  static const errorBackground = Color(0x1AEF4444);
  static const surface = Color(0xFF1A1F3A);
}