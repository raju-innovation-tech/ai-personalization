/// Centralized app constants. Nothing environment-sensitive (like secrets)
/// lives here — only stable, non-sensitive configuration values.
class AppConstants {
  AppConstants._();

  static const String appName = 'AI Personalization Admin';

  /// Default API base URL for local development (Desktop & Web).
  static const String defaultApiBaseUrl = 'http://localhost:8000/api/v1';

  /// Host LAN IP for direct Wi-Fi connections on physical mobile devices.
  static const String lanApiBaseUrl = 'http://192.168.1.28:8000/api/v1';

  /// Android emulator host alias.
  static const String emulatorApiBaseUrl = 'http://10.0.2.2:8000/api/v1';

  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: defaultApiBaseUrl,
  );

  // Secure storage keys
  static const String accessTokenKey = 'access_token';
  static const String refreshTokenKey = 'refresh_token';
  static const String serverUrlKey = 'custom_server_base_url';

  // Responsive breakpoints
  static const double mobileBreakpoint = 600;
  static const double tabletBreakpoint = 1024;
  static const double desktopBreakpoint = 1440;
}
