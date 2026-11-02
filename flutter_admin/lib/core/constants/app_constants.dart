/// Centralized app constants. Nothing environment-sensitive (like secrets)
/// lives here — only stable, non-sensitive configuration values.
class AppConstants {
  AppConstants._();

  static const String appName = 'AI Personalization Admin';

  /// Default API base URL for local development.
  ///
  /// IMPORTANT — Android emulator vs real device vs desktop/web:
  /// - Android emulator: use 10.0.2.2 (maps to host machine's localhost).
  /// - Real Android device over USB/WiFi: use your PC's LAN IP, e.g. http://192.168.1.23:8000
  /// - Windows/macOS/Linux desktop or Chrome web: http://localhost:8000 works directly.
  ///
  /// Override at build/run time with:
  ///   flutter run --dart-define=API_BASE_URL=http://192.168.1.23:8000/api/v1
  static const String defaultApiBaseUrl = 'http://localhost:8000/api/v1';

  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: defaultApiBaseUrl,
  );

  // Secure storage keys
  static const String accessTokenKey = 'access_token';
  static const String refreshTokenKey = 'refresh_token';

  // Responsive breakpoints
  static const double mobileBreakpoint = 600;
  static const double tabletBreakpoint = 1024;
  static const double desktopBreakpoint = 1440;
}
