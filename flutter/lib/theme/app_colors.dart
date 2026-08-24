import 'package:flutter/material.dart';

/// ExpiryGuard Clinical Pharmacy Design System — Color Tokens (v2.0)
class AppColors {
  // Core 6-Token Semantic Palette
  static const Color brandDeep = Color(0xFF0C3B34);      // Clinical Anchor / Primary Actions
  static const Color brandHover = Color(0xFF072B26);     // Pressed / Hover
  static const Color surfaceBg = Color(0xFFF8FAFC);      // Counter-Clean Canvas
  static const Color surfaceCard = Color(0xFFFFFFFF);    // Pure White Surfaces
  static const Color textPrimary = Color(0xFF0F172A);    // High-Density Slate Ink
  static const Color textMuted = Color(0xFF64748B);      // Secondary Labels / Metadata
  static const Color border = Color(0xFFE2E8F0);         // 1px Structural Divider

  // Operational Safety Status Tokens (Drug Safety & Expiry)
  static const Color statusSafe = Color(0xFF059669);     // Active Stock / Verified Batch
  static const Color statusSafeBg = Color(0xFFECFDF5);
  static const Color statusSafeText = Color(0xFF065F46);

  static const Color statusWarning = Color(0xFFD97706);  // Expiring Soon (30-60 Days)
  static const Color statusWarningBg = Color(0xFFFFFBEB);
  static const Color statusWarningText = Color(0xFF92400E);

  static const Color statusDanger = Color(0xFFDC2626);   // Expired Drug / Returns
  static const Color statusDangerBg = Color(0xFFFEF2F2);
  static const Color statusDangerText = Color(0xFF991B1B);

  static const Color statusInfo = Color(0xFF0284C7);     // OCR / HSN Info
  static const Color statusInfoBg = Color(0xFFF0F9FF);
  static const Color statusInfoText = Color(0xFF075985);

  // Dark Mode Tokens
  static const Color darkBg = Color(0xFF0B132B);
  static const Color darkSurface = Color(0xFF1C2541);
  static const Color darkBorder = Color(0xFF334155);
  static const Color darkTextPrimary = Color(0xFFF8FAFC);
  static const Color darkTextMuted = Color(0xFF94A3B8);
}
