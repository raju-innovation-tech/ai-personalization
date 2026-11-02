import 'package:flutter/material.dart';

/// Central color palette for the AI Personalization Engine.
/// Modern, high-contrast, responsive tech aesthetic (dark & light).
class AppColors {
  AppColors._();

  // Brand Accents
  static const Color primary = Color(0xFF6366F1); // Modern Electric Indigo
  static const Color primaryLight = Color(0xFF818CF8);
  static const Color primaryDark = Color(0xFF4F46E5);
  static const Color primaryGlow = Color(0x336366F1);
  static const Color accentCyan = Color(0xFF06B6D4);
  static const Color accentPurple = Color(0xFF8B5CF6);

  // Light theme surfaces
  static const Color backgroundLight = Color(0xFFF8FAFC);
  static const Color cardLight = Color(0xFFFFFFFF);
  static const Color cardLightElevated = Color(0xFFF1F5F9);
  static const Color textPrimaryLight = Color(0xFF0F172A);
  static const Color textSecondaryLight = Color(0xFF64748B);
  static const Color textTertiaryLight = Color(0xFF94A3B8);
  static const Color borderLight = Color(0xFFE2E8F0);

  // Dark theme surfaces (Obsidian / Slate Luxury Tech)
  static const Color backgroundDark = Color(0xFF0B0F17);
  static const Color cardDark = Color(0xFF141923);
  static const Color cardDarkElevated = Color(0xFF1C2331);
  static const Color textPrimaryDark = Color(0xFFF8FAFC);
  static const Color textSecondaryDark = Color(0xFF94A3B8);
  static const Color textTertiaryDark = Color(0xFF64748B);
  static const Color borderDark = Color(0xFF232B3B);

  // Semantic Indicators
  static const Color success = Color(0xFF10B981); // Emerald
  static const Color warning = Color(0xFFF59E0B); // Amber
  static const Color danger = Color(0xFFEF4444); // Crimson
  static const Color info = Color(0xFF3B82F6); // Blue
}
