import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../auth/domain/admin_user.dart';
import '../../../auth/presentation/providers/auth_controller.dart';
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

  /// Super Admin can only be one. Super Admin role can never be selected for a new user or granted to another user.
  List<UserRole> get _grantableRoles =>
      UserRole.values.where((r) => r != UserRole.superAdmin).toList();

  /// Admin cannot edit or touch Super Admin details
  bool get _locked => _editing && widget.user!.role == UserRole.superAdmin && !_currentIsSuperAdmin;

  /// Non-super-admin users can be deleted (except oneself)
  bool get _canDelete =>
      _editing && !_isSelf && widget.user!.role != UserRole.superAdmin && !_locked;

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
        final newEmail = _email.text.trim();
        await repository.update(
          original.id,
          email: newEmail.toLowerCase() == original.email.toLowerCase() ? null : newEmail,
          fullName: _name.text.trim() == original.fullName ? null : _name.text.trim(),
          role: _role == original.role ? null : _role,
          isActive: _active == original.isActive ? null : _active,
          password: _password.text.isEmpty ? null : _password.text,
        );
        if (_isSelf && mounted) {
          await ref.read(authControllerProvider.notifier).authenticateWithCurrentUser();
        }
      } else {
        await repository.create(
          email: _email.text.trim(),
          password: _password.text,
          fullName: _name.text.trim(),
          role: _role,
        );
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

  Future<void> _delete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete user?'),
        content: Text(
          'Are you sure you want to permanently delete "${widget.user!.email}" (${widget.user!.fullName})? This action cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.danger),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    setState(() {
      _saving = true;
      _error = null;
    });

    try {
      await ref.read(usersRepositoryProvider).delete(widget.user!.id);
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
        constraints: const BoxConstraints(maxWidth: 480, maxHeight: 660),
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
                      Expanded(
                        child: Text(
                          _editing ? 'Edit user' : 'New user',
                          style: textTheme.headlineSmall,
                        ),
                      ),
                      IconButton(
                        tooltip: 'Close',
                        icon: const Icon(Icons.close),
                        onPressed: _saving ? null : () => Navigator.of(context).pop(false),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (_locked) ...[
                    Container(
                      margin: const EdgeInsets.only(bottom: 12),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppColors.warning.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: AppColors.warning.withValues(alpha: 0.4)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.shield_outlined, color: AppColors.warning, size: 20),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'The Super Admin account is protected. Only the Super Admin can edit their own details.',
                              style: textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                  TextFormField(
                    controller: _email,
                    enabled: !_saving && !_locked,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(labelText: 'Email', isDense: true),
                    validator: (v) =>
                        _emailPattern.hasMatch((v ?? '').trim()) ? null : 'Enter a valid email address',
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _name,
                    enabled: !_saving && !_locked,
                    decoration: const InputDecoration(labelText: 'Full name', isDense: true),
                    validator: (v) =>
                        _editing && (v ?? '').trim().isEmpty ? 'Name cannot be empty' : null,
                  ),
                  const SizedBox(height: 12),
                  InputDecorator(
                    decoration: InputDecoration(
                      labelText: 'Role',
                      isDense: true,
                      helperText: _isSelf
                          ? 'You cannot change your own role'
                          : (_role == UserRole.superAdmin ? 'Super Admin role cannot be reassigned' : null),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    ),
                    child: DropdownButtonHideUnderline(
                      child: DropdownButton<UserRole>(
                        isExpanded: true,
                        isDense: true,
                        value: _role,
                        items: [
                          for (final role in roleItems)
                            DropdownMenuItem(value: role, child: Text(role.displayName))
                        ],
                        onChanged: (_saving || _isSelf || _locked || _role == UserRole.superAdmin)
                            ? null
                            : (value) => setState(() => _role = value ?? _role),
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
                      subtitle: Text(
                        _isSelf
                            ? 'You cannot deactivate yourself'
                            : (_role == UserRole.superAdmin
                                ? 'Super Admin cannot be deactivated'
                                : 'Inactive users cannot sign in'),
                      ),
                      value: _active,
                      onChanged: (_saving || _isSelf || _locked || _role == UserRole.superAdmin)
                          ? null
                          : (value) => setState(() => _active = value),
                    ),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 8),
                    Text(_error!, style: const TextStyle(color: AppColors.danger)),
                  ],
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      if (_canDelete)
                        TextButton.icon(
                          style: TextButton.styleFrom(foregroundColor: AppColors.danger),
                          onPressed: _saving ? null : _delete,
                          icon: const Icon(Icons.delete_outline, size: 18),
                          label: const Text('Delete user'),
                        ),
                      const Spacer(),
                      TextButton(
                        onPressed: _saving ? null : () => Navigator.of(context).pop(false),
                        child: const Text('Cancel'),
                      ),
                      const SizedBox(width: 8),
                      FilledButton(
                        onPressed: (_saving || _locked) ? null : _save,
                        child: _saving
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
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
