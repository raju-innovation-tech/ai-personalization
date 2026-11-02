import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../storage/preferences_storage.dart';

const String kThemeModeKey = 'theme_mode';

ThemeMode themeModeFromString(String? value) {
  switch (value) {
    case 'light':
      return ThemeMode.light;
    case 'dark':
      return ThemeMode.dark;
    default:
      return ThemeMode.system;
  }
}

String themeModeToString(ThemeMode mode) {
  switch (mode) {
    case ThemeMode.light:
      return 'light';
    case ThemeMode.dark:
      return 'dark';
    case ThemeMode.system:
      return 'system';
  }
}

/// Holds the chosen theme mode and remembers it between launches.
class ThemeController extends StateNotifier<ThemeMode> {
  ThemeController(this._storage) : super(ThemeMode.system) {
    _load();
  }

  final PreferencesStorage _storage;

  Future<void> _load() async {
    try {
      final saved = await _storage.read(kThemeModeKey);
      if (mounted) state = themeModeFromString(saved);
    } catch (_) {
      // Storage unavailable: keep following the system theme.
    }
  }

  Future<void> setMode(ThemeMode mode) async {
    state = mode;
    try {
      await _storage.write(kThemeModeKey, themeModeToString(mode));
    } catch (_) {
      // Not being able to persist the choice must never break the UI.
    }
  }

  /// Flip between light and dark based on what the user currently sees.
  Future<void> toggle(Brightness current) =>
      setMode(current == Brightness.dark ? ThemeMode.light : ThemeMode.dark);
}

final preferencesStorageProvider = Provider<PreferencesStorage>((ref) => PreferencesStorage());

final themeModeProvider = StateNotifierProvider<ThemeController, ThemeMode>((ref) {
  return ThemeController(ref.watch(preferencesStorageProvider));
});
