/// Mirrors backend UserRole enum (app.database.models.user.UserRole).
enum UserRole {
  superAdmin('SUPER_ADMIN'),
  admin('ADMIN'),
  marketingManager('MARKETING_MANAGER'),
  dataAnalyst('DATA_ANALYST'),
  viewer('VIEWER');

  const UserRole(this.value);
  final String value;

  static UserRole fromString(String value) {
    return UserRole.values.firstWhere(
      (r) => r.value == value,
      orElse: () => UserRole.viewer,
    );
  }

  String get displayName {
    switch (this) {
      case UserRole.superAdmin:
        return 'Super Admin';
      case UserRole.admin:
        return 'Admin';
      case UserRole.marketingManager:
        return 'Marketing Manager';
      case UserRole.dataAnalyst:
        return 'Data Analyst';
      case UserRole.viewer:
        return 'Viewer';
    }
  }
}

class AdminUser {
  const AdminUser({
    required this.id,
    required this.email,
    required this.fullName,
    required this.role,
    required this.isActive,
  });

  final String id;
  final String email;
  final String fullName;
  final UserRole role;
  final bool isActive;

  factory AdminUser.fromJson(Map<String, dynamic> json) {
    return AdminUser(
      id: json['id'] as String,
      email: json['email'] as String,
      fullName: json['full_name'] as String,
      role: UserRole.fromString(json['role'] as String),
      isActive: json['is_active'] as bool,
    );
  }
}
