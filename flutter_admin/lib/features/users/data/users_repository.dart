import '../../../core/network/api_client.dart';
import '../../auth/domain/admin_user.dart';
import '../domain/staff_user.dart';

class UsersRepository {
  UsersRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<List<StaffUser>> list() async {
    final response = await _apiClient.get('/users');
    final data = response['data'] as Map<String, dynamic>;
    return (data['items'] as List<dynamic>? ?? const [])
        .map((e) => StaffUser.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<StaffUser> create({
    required String email,
    required String password,
    required String fullName,
    required UserRole role,
  }) async {
    final response = await _apiClient.post(
      '/users',
      data: {
        'email': email.trim(),
        'password': password,
        'full_name': fullName.trim().isEmpty ? null : fullName.trim(),
        'role': role.value,
      },
    );
    return StaffUser.fromJson(response['data'] as Map<String, dynamic>);
  }

  /// Only the fields that are not null are sent.
  Future<StaffUser> update(
    String id, {
    String? email,
    String? fullName,
    UserRole? role,
    bool? isActive,
    String? password,
  }) async {
    final body = <String, dynamic>{
      if (email != null && email.trim().isNotEmpty) 'email': email.trim(),
      if (fullName != null) 'full_name': fullName.trim(),
      if (role != null) 'role': role.value,
      if (isActive != null) 'is_active': isActive,
      if (password != null && password.isNotEmpty) 'password': password,
    };
    final response = await _apiClient.patch('/users/$id', data: body);
    return StaffUser.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<void> delete(String id) async {
    await _apiClient.delete('/users/$id');
  }
}
