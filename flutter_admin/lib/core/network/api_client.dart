import 'dart:io' show Platform;

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:logger/logger.dart';

import '../constants/app_constants.dart';
import '../errors/app_failure.dart';
import '../storage/secure_token_storage.dart';

/// Thin wrapper around Dio, configured with:
///  - Dynamic base URL with cross-device auto-fallback (Wi-Fi LAN IP, localhost, emulator)
///  - JSON base options + timeouts
///  - Bearer token attachment
///  - Automatic access-token refresh on 401 (single retry)
///  - Consistent AppFailure mapping for callers
class ApiClient {
  ApiClient({required SecureTokenStorage tokenStorage, required this.onUnauthorized})
      : _tokenStorage = tokenStorage,
        _logger = Logger(printer: SimplePrinter(colors: false)) {
    final initialUrl = _resolveInitialUrl();
    _dio = Dio(
      BaseOptions(
        baseUrl: initialUrl,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 15),
        headers: {'Content-Type': 'application/json'},
      ),
    );

    _refreshDio = Dio(BaseOptions(baseUrl: initialUrl));

    _initCustomUrl();

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

  final void Function() onUnauthorized;

  Future<bool>? _refreshInFlight;

  String get baseUrl => _dio.options.baseUrl;

  static String _resolveInitialUrl() {
    const envUrl = String.fromEnvironment('API_BASE_URL');
    if (envUrl.isNotEmpty) return envUrl;

    if (kIsWeb) return AppConstants.defaultApiBaseUrl;

    if (Platform.isAndroid) {
      // On physical Android devices, direct Wi-Fi LAN IP connects directly without ADB reverse.
      return AppConstants.lanApiBaseUrl;
    }

    return AppConstants.defaultApiBaseUrl;
  }

  List<String> get candidateUrls {
    return {
      _dio.options.baseUrl,
      AppConstants.lanApiBaseUrl,
      AppConstants.defaultApiBaseUrl,
      AppConstants.emulatorApiBaseUrl,
    }.toList();
  }

  void _initCustomUrl() async {
    try {
      final saved = await _tokenStorage.getServerUrl();
      if (saved != null && saved.isNotEmpty && saved != _dio.options.baseUrl) {
        _dio.options.baseUrl = saved;
        _refreshDio.options.baseUrl = saved;
      }
    } catch (_) {}
  }

  void updateBaseUrl(String newUrl) {
    var url = newUrl.trim();
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'http://$url';
    }
    if (!url.endsWith('/api/v1')) {
      if (url.endsWith('/')) {
        url = '${url}api/v1';
      } else {
        url = '$url/api/v1';
      }
    }
    _dio.options.baseUrl = url;
    _refreshDio.options.baseUrl = url;
    _tokenStorage.saveServerUrl(url);
    _logger.i('Active API base URL updated to: $url');
  }

  Future<bool> pingServer([String? testUrl]) async {
    try {
      final url = testUrl ?? _dio.options.baseUrl;
      final dio = Dio(BaseOptions(
        baseUrl: url,
        connectTimeout: const Duration(seconds: 4),
        receiveTimeout: const Duration(seconds: 4),
      ));
      final res = await dio.get('/health');
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

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
      if (e.type == DioExceptionType.connectionError) {
        // Automatic fallback candidate probe
        for (final candidate in candidateUrls) {
          if (candidate == _dio.options.baseUrl) continue;
          try {
            _logger.i('Connection failed to ${_dio.options.baseUrl}. Trying candidate: $candidate');
            _dio.options.baseUrl = candidate;
            _refreshDio.options.baseUrl = candidate;
            final fallbackResponse = await call();
            if (fallbackResponse.data is Map<String, dynamic>) {
              _logger.i('Successfully connected via candidate: $candidate');
              _tokenStorage.saveServerUrl(candidate);
              return fallbackResponse.data as Map<String, dynamic>;
            }
          } catch (_) {
            // Keep trying next candidate
          }
        }
      }
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
