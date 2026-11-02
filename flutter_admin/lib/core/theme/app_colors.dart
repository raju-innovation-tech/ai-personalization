import 'package:flutter/material.dart';

/// Central color palette, per project spec (§2 — recommended colors).
class AppColors {
  AppColors._();

  // Brand
  static const Color primary = Color(0xFF4F46E5); // Indigo
  static const Color primaryLight = Color(0xFF818CF8);
  static const Color primaryDark = Color(0xFF3730A3);

  // Light theme surfaces
  static const Color backgroundLight = Color(0xFFF7F8FA);
  static const Color cardLight = Color(0xFFFFFFFF);
  static const Color textPrimaryLight = Color(0xFF1F2937);
  static const Color textSecondaryLight = Color(0xFF6B7280);
  static const Color borderLight = Color(0xFFE5E7EB);

  // Dark theme surfaces
  static const Color backgroundDark = Color(0xFF0F1115);
  static const Color cardDark = Color(0xFF1A1D23);
  static const Color textPrimaryDark = Color(0xFFF3F4F6);
  static const Color textSecondaryDark = Color(0xFF9CA3AF);
  static const Color borderDark = Color(0xFF2D3139);

  // Semantic
  static const Color success = Color(0xFF16A34A);
  static const Color warning = Color(0xFFD97706);
  static const Color danger = Color(0xFFDC2626);
  static const Color info = Color(0xFF2563EB);
}
