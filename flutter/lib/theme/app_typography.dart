import 'package:flutter/material.dart';
import 'app_colors.dart';

/// ExpiryGuard Clinical Pharmacy Design System — Typography & Numeric Scales
class AppTypography {
  static const String fontUi = 'Inter';
  static const String fontMono = 'JetBrainsMono';

  // Headings
  static const TextStyle displayLarge = TextStyle(
    fontFamily: fontUi,
    fontSize: 24,
    fontWeight: FontWeight.w700,
    height: 1.3,
    color: AppColors.textPrimary,
    letterSpacing: -0.5,
  );

  static const TextStyle sectionTitle = TextStyle(
    fontFamily: fontUi,
    fontSize: 18,
    fontWeight: FontWeight.w600,
    height: 1.35,
    color: AppColors.textPrimary,
    letterSpacing: -0.3,
  );

  static const TextStyle cardTitle = TextStyle(
    fontFamily: fontUi,
    fontSize: 15,
    fontWeight: FontWeight.w600,
    height: 1.4,
    color: AppColors.textPrimary,
  );

  // Body Text
  static const TextStyle body = TextStyle(
    fontFamily: fontUi,
    fontSize: 13.5,
    fontWeight: FontWeight.w400,
    height: 1.5,
    color: AppColors.textPrimary,
  );

  static const TextStyle bodyMedium = TextStyle(
    fontFamily: fontUi,
    fontSize: 13.5,
    fontWeight: FontWeight.w500,
    height: 1.5,
    color: AppColors.textPrimary,
  );

  static const TextStyle bodyMuted = TextStyle(
    fontFamily: fontUi,
    fontSize: 12,
    fontWeight: FontWeight.w400,
    height: 1.4,
    color: AppColors.textMuted,
  );

  static const TextStyle badge = TextStyle(
    fontFamily: fontUi,
    fontSize: 11.5,
    fontWeight: FontWeight.w600,
    height: 1.2,
  );

  // Dedicated Tabular Numerics for Invoicing, Batch Codes, and Prices
  static const TextStyle numericGrandTotal = TextStyle(
    fontFamily: fontMono,
    fontSize: 22,
    fontWeight: FontWeight.w700,
    color: AppColors.brandDeep,
    letterSpacing: -0.5,
    fontFeatures: [FontFeature.tabularFigures()],
  );

  static const TextStyle numericPrice = TextStyle(
    fontFamily: fontMono,
    fontSize: 14,
    fontWeight: FontWeight.w600,
    color: AppColors.textPrimary,
    fontFeatures: [FontFeature.tabularFigures()],
  );

  static const TextStyle numericBatch = TextStyle(
    fontFamily: fontMono,
    fontSize: 12,
    fontWeight: FontWeight.w600,
    color: AppColors.textPrimary,
    letterSpacing: 0.2,
    fontFeatures: [FontFeature.tabularFigures()],
  );

  static const TextStyle numericDate = TextStyle(
    fontFamily: fontMono,
    fontSize: 12.5,
    fontWeight: FontWeight.w500,
    color: AppColors.textMuted,
    fontFeatures: [FontFeature.tabularFigures()],
  );
}
