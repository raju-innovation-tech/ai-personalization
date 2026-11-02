import 'package:flutter/material.dart';

import 'app_colors.dart';

/// Modern Material 3 light/dark themes with high-contrast surfaces,
/// refined typography, and smooth responsiveness across all screen sizes.
class AppTheme {
  AppTheme._();

  static ThemeData get light => _build(Brightness.light);
  static ThemeData get dark => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final isDark = brightness == Brightness.dark;

    final colorScheme = ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: brightness,
      primary: AppColors.primary,
      error: AppColors.danger,
      surface: isDark ? AppColors.cardDark : AppColors.cardLight,
    );

    final textPrimary = isDark ? AppColors.textPrimaryDark : AppColors.textPrimaryLight;
    final textSecondary = isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight;
    final border = isDark ? AppColors.borderDark : AppColors.borderLight;

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: isDark ? AppColors.backgroundDark : AppColors.backgroundLight,
      fontFamily: 'Roboto',
      textTheme: TextTheme(
        headlineMedium: TextStyle(fontWeight: FontWeight.w800, color: textPrimary, fontSize: 26, letterSpacing: -0.5),
        headlineSmall: TextStyle(fontWeight: FontWeight.w700, color: textPrimary, fontSize: 22, letterSpacing: -0.3),
        titleLarge: TextStyle(fontWeight: FontWeight.w700, color: textPrimary, fontSize: 18, letterSpacing: -0.2),
        titleMedium: TextStyle(fontWeight: FontWeight.w600, color: textPrimary, fontSize: 16),
        bodyLarge: TextStyle(color: textPrimary, fontSize: 15, height: 1.4),
        bodyMedium: TextStyle(color: textSecondary, fontSize: 14, height: 1.4),
        labelLarge: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14, letterSpacing: 0.1),
      ),
      cardTheme: CardThemeData(
        color: isDark ? AppColors.cardDark : AppColors.cardLight,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: border, width: 1),
        ),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: isDark ? AppColors.backgroundDark : AppColors.backgroundLight,
        foregroundColor: textPrimary,
        elevation: 0,
        scrolledUnderElevation: 1,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: TextStyle(
          color: textPrimary,
          fontSize: 18,
          fontWeight: FontWeight.w700,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: Colors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: textPrimary,
          side: BorderSide(color: border),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: isDark ? AppColors.cardDarkElevated : Colors.white,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.8),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.danger),
        ),
      ),
      dividerTheme: DividerThemeData(color: border, thickness: 1),
      dataTableTheme: DataTableThemeData(
        headingRowColor: WidgetStatePropertyAll(isDark ? AppColors.cardDarkElevated : const Color(0xFFF1F5F9)),
        headingTextStyle: TextStyle(fontWeight: FontWeight.w700, color: textSecondary, fontSize: 13, letterSpacing: 0.3),
        dataTextStyle: TextStyle(color: textPrimary, fontSize: 14),
        horizontalMargin: 20,
        columnSpacing: 24,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: isDark ? AppColors.cardDark : AppColors.cardLight,
        elevation: 6,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(color: border),
        ),
      ),
    );
  }
}
