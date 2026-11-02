/// Unified failure type surfaced to the UI layer. Wraps the backend's
/// {success:false, error:{code,message}} envelope or a transport-level
/// problem (no connection, timeout, unexpected shape).
class AppFailure {
  const AppFailure({required this.code, required this.message});

  final String code;
  final String message;

  factory AppFailure.network() =>
      const AppFailure(code: 'NETWORK_ERROR', message: 'Could not reach the server. Check your connection.');

  factory AppFailure.timeout() =>
      const AppFailure(code: 'TIMEOUT', message: 'The request timed out. Please try again.');

  factory AppFailure.unauthorized() =>
      const AppFailure(code: 'UNAUTHORIZED', message: 'Your session has expired. Please log in again.');

  factory AppFailure.unknown([String? detail]) =>
      AppFailure(code: 'UNKNOWN_ERROR', message: detail ?? 'Something went wrong. Please try again.');

  @override
  String toString() => 'AppFailure($code: $message)';
}

class AppException implements Exception {
  AppException(this.failure);
  final AppFailure failure;

  @override
  String toString() => failure.toString();
}

/// Human-readable message for anything thrown by the data layer.
String errorMessageOf(Object error) {
  if (error is AppException) return error.failure.message;
  return 'Something went wrong. Please try again.';
}
