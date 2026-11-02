import 'package:dio/dio.dart';
import 'package:logger/logger.dart';

import '../constants/app_constants.dart';
import '../errors/app_failure.dart';
import '../storage/secure_token_storage.dart';

/// Thin wrapper around Dio, configured with:
///  - JSON base options + timeouts
///  - Bearer token attachment
///  - Automatic access-token refresh on 401 (single retry)
///  - Consistent AppFailure mapping for callers
///
/// The refresh-token call itself must bypass this client's interceptor
/// (it uses a bare Dio instance) to avoid infinite refresh loops.
class ApiClient {
  ApiClient({required SecureTokenStorage tokenStorage, required this.onUnauthorized})
      : _tokenStorage = tokenStorage,
        _logger = Logger(printer: SimplePrinter(colors: false)) {
    _dio = Dio(
      BaseOptions(
        baseUrl: AppConstants.apiBaseUrl,
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 15),
        headers: {'Content-Type': 'application/json'},
      ),
    );

    _refreshDio = Dio(BaseOptions(baseUrl: AppConstants.apiBaseUrl));

    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _tokenStorage.getAccessToken();
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (DioException error, handler) async {
          final isUnauthorized = error.response?.statusCode == 401;
          final isRetry = error.requestOptions.extra['retried'] == true;
          // A 401 from login/refresh means "wrong credentials / dead refresh
          // token", not "expired access token" - never try to refresh for those.
          final path = error.requestOptions.path;
          final isAuthCall = path.contains('/auth/login') || path.contains('/auth/refresh');

          if (isUnauthorized && !isRetry && !isAuthCall) {
            final refreshed = await _tryRefreshToken();
            if (refreshed) {
              final retryOptions = error.requestOptions;
              retryOptions.extra['retried'] = true;
              final token = await _tokenStorage.getAccessToken();
              retryOptions.headers['Authorization'] = 'Bearer $token';
              try {
                final response = await _dio.fetch(retryOptions);
                return handler.resolve(response);
              } catch (_) {
                // fall through to unauthorized handling below
              }
            }
            await _tokenStorage.clear();
            onUnauthorized();
          }

          handler.next(error);
        },
      ),
    );
  }

  late final Dio _dio;
  late final Dio _refreshDio;
  final SecureTokenStorage _tokenStorage;
  final Logger _logger;

  /// Called when the session cannot be recovered — the app should route
  /// back to the login screen.
  final void Function() onUnauthorized;

  /// Single-flight: if several requests get a 401 at the same time they all
  /// share ONE refresh call. The backend rotates refresh tokens, so a second
  /// concurrent refresh with the same token would be rejected and log the
  /// user out.
  Future<bool>? _refreshInFlight;

  Future<bool> _tryRefreshToken() {
    return _refreshInFlight ??= _doRefreshToken().whenComplete(() => _refreshInFlight = null);
  }

  Future<bool> _doRefreshToken() async {
    final refreshToken = await _tokenStorage.getRefreshToken();
    if (refreshToken == null) return false;

    try {
      final response = await _refreshDio.post(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
      );
      final data = response.data['data'] as Map<String, dynamic>;
      await _tokenStorage.saveTokens(
        accessToken: data['access_token'] as String,
        refreshToken: data['refresh_token'] as String,
      );
      return true;
    } catch (e) {
      _logger.w('Token refresh failed: $e');
      return false;
    }
  }

  Future<Map<String, dynamic>> get(String path, {Map<String, dynamic>? queryParameters}) =>
      _request(() => _dio.get(path, queryParameters: queryParameters));

  Future<Map<String, dynamic>> post(String path, {Object? data}) =>
      _request(() => _dio.post(path, data: data));

  Future<Map<String, dynamic>> put(String path, {Object? data}) =>
      _request(() => _dio.put(path, data: data));

  Future<Map<String, dynamic>> patch(String path, {Object? data}) =>
      _request(() => _dio.patch(path, data: data));

  Future<Map<String, dynamic>> delete(String path) => _request(() => _dio.delete(path));

  Future<Map<String, dynamic>> _request(Future<Response> Function() call) async {
    try {
      final response = await call();
      if (response.data is Map<String, dynamic>) {
        return response.data as Map<String, dynamic>;
      }
      throw AppException(AppFailure.unknown('Unexpected response shape'));
    } on DioException catch (e) {
      throw AppException(_mapDioException(e));
    }
  }

  AppFailure _mapDioException(DioException e) {
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout ||
        e.type == DioExceptionType.sendTimeout) {
      return AppFailure.timeout();
    }
    if (e.type == DioExceptionType.connectionError) {
      return AppFailure.network();
    }

    final responseData = e.response?.data;
    if (responseData is Map<String, dynamic> && responseData['error'] is Map<String, dynamic>) {
      final error = responseData['error'] as Map<String, dynamic>;
      return AppFailure(
        code: error['code']?.toString() ?? 'UNKNOWN_ERROR',
        message: error['message']?.toString() ?? 'Something went wrong',
      );
    }

    if (e.response?.statusCode == 401) return AppFailure.unauthorized();

    return AppFailure.unknown(e.message);
  }
}
