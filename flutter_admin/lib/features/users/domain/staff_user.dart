import '../../auth/domain/admin_user.dart';

/// A staff account as listed by `GET /users` (not the logged-in user's session object).
class StaffUser {
  const StaffUser({
    required this.id,
    required this.email,
    required this.fullName,
    required this.role,
    required this.isActive,
    this.createdAt,
  });

  final String id;
  final String email;
  final String fullName;
  final UserRole role;
  final bool isActive;
  final String? createdAt;

  factory StaffUser.fromJson(Map<String, dynamic> json) {
    return StaffUser(
      id: json['id'] as String,
      email: json['email'] as String,
      fullName: json['full_name'] as String? ?? '',
      role: UserRole.fromString(json['role'] as String? ?? 'VIEWER'),
      isActive: json['is_active'] as bool? ?? true,
      createdAt: json['created_at'] as String?,
    );
  }
}
