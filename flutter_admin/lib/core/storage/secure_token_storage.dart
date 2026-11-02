import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../constants/app_constants.dart';

/// Wraps flutter_secure_storage for JWT access/refresh tokens.
/// Uses Keychain on iOS/macOS, Keystore-backed EncryptedSharedPreferences
/// on Android, and falls back appropriately on desktop/web.
class SecureTokenStorage {
  SecureTokenStorage({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  final FlutterSecureStorage _storage;

  Future<void> saveTokens({required String accessToken, required String refreshToken}) async {
    await _storage.write(key: AppConstants.accessTokenKey, value: accessToken);
    await _storage.write(key: AppConstants.refreshTokenKey, value: refreshToken);
  }

  Future<String?> getAccessToken() => _storage.read(key: AppConstants.accessTokenKey);

  Future<String?> getRefreshToken() => _storage.read(key: AppConstants.refreshTokenKey);

  Future<void> saveServerUrl(String url) async => _storage.write(key: AppConstants.serverUrlKey, value: url);

  Future<String?> getServerUrl() => _storage.read(key: AppConstants.serverUrlKey);

  Future<void> clear() async {
    await _storage.delete(key: AppConstants.accessTokenKey);
    await _storage.delete(key: AppConstants.refreshTokenKey);
  }
}
