import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../auth/domain/admin_user.dart';
import '../../domain/staff_user.dart';
import '../providers/users_providers.dart';

final RegExp _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

/// Create (user == null) or edit a staff user. Pops `true` when something was saved.
class UserFormDialog extends ConsumerStatefulWidget {
  const UserFormDialog({super.key, required this.currentUser, this.user});

  /// The logged-in admin (decides which roles may be granted and blocks self-lockout).
  final AdminUser currentUser;
  final StaffUser? user;

  @override
  ConsumerState<UserFormDialog> createState() => _UserFormDialogState();
}

class _UserFormDialogState extends ConsumerState<UserFormDialog> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  late final TextEditingController _email;
  late final TextEditingController _name;
  late final TextEditingController _password;

  UserRole _role = UserRole.viewer;
  bool _active = true;
  bool _saving = false;
  String? _error;

  bool get _editing => widget.user != null;
  bool get _isSelf => widget.user?.id == widget.currentUser.id;
  bool get _currentIsSuperAdmin => widget.currentUser.role == UserRole.superAdmin;

  /// Admins may not hand out (or touch) the Super Admin role; the API enforces the same rule.
  List<UserRole> get _grantableRoles =>
      UserRole.values.where((r) => r != UserRole.superAdmin || _currentIsSuperAdmin).toList();

  bool get _locked => _editing && widget.user!.role == UserRole.superAdmin && !_currentIsSuperAdmin;

  @override
  void initState() {
    super.initState();
    final user = widget.user;
    _email = TextEditingController(text: user?.email ?? '');
    _name = TextEditingController(text: user?.fullName ?? '');
    _password = TextEditingController();
    if (user != null) {
      _role = user.role;
      _active = user.isActive;
    }
  }

  @override
  void dispose() {
    _email.dispose();
    _name.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final repository = ref.read(usersRepositoryProvider);
      if (_editing) {
        final original = widget.user!;
        await repository.update(
          original.id,
          fullName: _name.text.trim() == original.fullName ? null : _name.text.trim(),
          role: _role == original.role ? null : _role,
          isActive: _active == original.isActive ? null : _active,
          password: _password.text.isEmpty ? null : _password.text,
        );
      } else {
        await repository.create(email: _email.text, password: _password.text, fullName: _name.text, role: _role);
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = errorMessageOf(error);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final roles = _grantableRoles;
    final roleItems = roles.contains(_role) ? roles : [...roles, _role];

    return Dialog(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480, maxHeight: 640),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(child: Text(_editing ? 'Edit user' : 'New user', style: textTheme.headlineSmall)),
                      IconButton(
                        tooltip: 'Close',
                        icon: const Icon(Icons.close),
                        onPressed: _saving ? null : () => Navigator.of(context).pop(false),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _email,
                    enabled: !_editing && !_saving,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(labelText: 'Email', isDense: true),
                    validator: (v) => _emailPattern.hasMatch((v ?? '').trim()) ? null : 'Enter a valid email address',
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _name,
                    enabled: !_saving && !_locked,
                    decoration: const InputDecoration(labelText: 'Full name', isDense: true),
                    validator: (v) => _editing && (v ?? '').trim().isEmpty ? 'Name cannot be empty' : null,
                  ),
                  const SizedBox(height: 12),
                  InputDecorator(
                    decoration: InputDecoration(
                      labelText: 'Role',
                      isDense: true,
                      helperText: _isSelf ? 'You cannot change your own role' : null,
                      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    ),
                    child: DropdownButtonHideUnderline(
                      child: DropdownButton<UserRole>(
                        isExpanded: true,
                        isDense: true,
                        value: _role,
                        items: [for (final role in roleItems) DropdownMenuItem(value: role, child: Text(role.displayName))],
                        onChanged: (_saving || _isSelf || _locked) ? null : (value) => setState(() => _role = value ?? _role),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _password,
                    enabled: !_saving && !_locked,
                    obscureText: true,
                    decoration: InputDecoration(
                      labelText: _editing ? 'New password (leave empty to keep)' : 'Password',
                      helperText: 'At least 8 characters. Changing it signs the user out everywhere.',
                      isDense: true,
                    ),
                    validator: (v) {
                      final text = v ?? '';
                      if (!_editing && text.length < 8) return 'At least 8 characters';
                      if (_editing && text.isNotEmpty && text.length < 8) return 'At least 8 characters';
                      return null;
                    },
                  ),
                  if (_editing) ...[
                    const SizedBox(height: 8),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Account active'),
                      subtitle: Text(_isSelf ? 'You cannot deactivate yourself' : 'Inactive users cannot sign in'),
                      value: _active,
                      onChanged: (_saving || _isSelf || _locked) ? null : (value) => setState(() => _active = value),
                    ),
                  ],
                  if (_locked)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text('Only a Super Admin can change this account.', style: textTheme.bodyMedium),
                    ),
                  if (_error != null) ...[
                    const SizedBox(height: 8),
                    Text(_error!, style: const TextStyle(color: AppColors.danger)),
                  ],
                  const SizedBox(height: 16),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      TextButton(
                        onPressed: _saving ? null : () => Navigator.of(context).pop(false),
                        child: const Text('Cancel'),
                      ),
                      const SizedBox(width: 8),
                      FilledButton(
                        onPressed: (_saving || _locked) ? null : _save,
                        child: _saving
                            ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                            : Text(_editing ? 'Save changes' : 'Create user'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
