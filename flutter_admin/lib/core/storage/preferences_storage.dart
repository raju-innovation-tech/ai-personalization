import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Tiny key-value store for UI preferences (theme mode). Reuses flutter_secure_storage so no extra package is needed.
class PreferencesStorage {
  PreferencesStorage({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  final FlutterSecureStorage _storage;

  Future<String?> read(String key) => _storage.read(key: key);

  Future<void> write(String key, String value) => _storage.write(key: key, value: value);
}
