import '../../../core/network/api_client.dart';
import '../../../core/storage/secure_token_storage.dart';
import '../domain/admin_user.dart';

class AuthRepository {
  AuthRepository({required ApiClient apiClient, required SecureTokenStorage tokenStorage})
      : _apiClient = apiClient,
        _tokenStorage = tokenStorage;

  final ApiClient _apiClient;
  final SecureTokenStorage _tokenStorage;

  Future<AdminUser> login({required String email, required String password}) async {
    final response = await _apiClient.post('/auth/login', data: {
      'email': email,
      'password': password,
    });

    final data = response['data'] as Map<String, dynamic>;
    await _tokenStorage.saveTokens(
      accessToken: data['access_token'] as String,
      refreshToken: data['refresh_token'] as String,
    );

    return fetchCurrentUser();
  }

  Future<AdminUser> fetchCurrentUser() async {
    final response = await _apiClient.get('/auth/me');
    final data = response['data'] as Map<String, dynamic>;
    return AdminUser.fromJson(data);
  }

  Future<void> logout() async {
    try {
      await _apiClient.post('/auth/logout');
    } catch (_) {
      // Server unreachable / token already expired: still log out locally.
    } finally {
      await _tokenStorage.clear();
    }
  }

  Future<bool> hasStoredSession() async {
    final token = await _tokenStorage.getAccessToken();
    return token != null;
  }

  Future<Map<String, dynamic>> requestPasswordReset(String email) async {
    final response = await _apiClient.post('/auth/forgot-password', data: {
      'email': email,
    });
    return response['data'] as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> resetPassword({
    required String email,
    required String code,
    required String newPassword,
  }) async {
    final response = await _apiClient.post('/auth/reset-password', data: {
      'email': email,
      'code': code,
      'new_password': newPassword,
    });
    final data = response['data'] as Map<String, dynamic>;
    if (data['access_token'] != null && data['refresh_token'] != null) {
      await _tokenStorage.saveTokens(
        accessToken: data['access_token'] as String,
        refreshToken: data['refresh_token'] as String,
      );
    }
    return data;
  }
}
