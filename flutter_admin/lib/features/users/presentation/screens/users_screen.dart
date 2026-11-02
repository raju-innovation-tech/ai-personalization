import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../../auth/presentation/providers/auth_controller.dart';
import '../../../auth/presentation/providers/auth_state.dart';
import '../../domain/staff_user.dart';
import '../providers/users_providers.dart';
import '../widgets/user_form_dialog.dart';

class UsersScreen extends ConsumerWidget {
  const UsersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final usersAsync = ref.watch(usersProvider);
    final auth = ref.watch(authControllerProvider);
    final currentUser = auth is AuthAuthenticated ? auth.user : null;

    Future<void> openForm({StaffUser? user}) async {
      if (currentUser == null) return;
      final saved = await showDialog<bool>(
        context: context,
        builder: (_) => UserFormDialog(currentUser: currentUser, user: user),
      );
      if (saved == true && context.mounted) ref.invalidate(usersProvider);
    }

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Users', style: textTheme.headlineSmall),
                    const SizedBox(height: 4),
                    Text(
                      'Staff who can sign in to this dashboard, plus service accounts for your shop.',
                      style: textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              FilledButton.icon(
                onPressed: currentUser == null ? null : () => openForm(),
                icon: const Icon(Icons.person_add_alt_1_outlined, size: 20),
                label: const Text('New user'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          usersAsync.when(
            loading: () => const Padding(padding: EdgeInsets.all(32), child: LoadingState(message: 'Loading users...')),
            error: (error, _) => ErrorState(
              message: errorMessageOf(error),
              onRetry: () => ref.invalidate(usersProvider),
            ),
            data: (users) {
              if (users.isEmpty) {
                return const EmptyState(title: 'No users yet', subtitle: 'Create the first one.', icon: Icons.people_outline);
              }
              return Card(
                clipBehavior: Clip.antiAlias,
                child: Column(
                  children: [
                    for (var i = 0; i < users.length; i++) ...[
                      if (i > 0) const Divider(height: 1),
                      _UserRow(
                        user: users[i],
                        isYou: users[i].id == currentUser?.id,
                        onEdit: () => openForm(user: users[i]),
                      ),
                    ],
                  ],
                ),
              );
            },
          ),
          const SizedBox(height: 12),
          Text(
            'Roles: Super Admin and Admin manage everything; Marketing Manager manages offers and uses the checkout API; '
            'Data Analyst and Viewer are read-only.',
            style: textTheme.bodyMedium?.copyWith(fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _UserRow extends StatelessWidget {
  const _UserRow({required this.user, required this.isYou, required this.onEdit});

  final StaffUser user;
  final bool isYou;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final statusColor = user.isActive ? AppColors.success : AppColors.danger;
    final initial = (user.fullName.isNotEmpty ? user.fullName : user.email)[0].toUpperCase();

    return InkWell(
      onTap: onEdit,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            CircleAvatar(
              radius: 20,
              backgroundColor: AppColors.primary.withValues(alpha: 0.12),
              child: Text(initial, style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isYou ? '${user.fullName} (you)' : user.fullName,
                    style: textTheme.titleMedium?.copyWith(fontSize: 14),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    user.email,
                    style: textTheme.bodyMedium?.copyWith(fontSize: 12),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(user.role.displayName, style: textTheme.bodyLarge?.copyWith(fontSize: 13)),
                const SizedBox(height: 4),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: statusColor.withValues(alpha: 0.13),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    user.isActive ? 'Active' : 'Disabled',
                    style: TextStyle(color: statusColor, fontSize: 11, fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
            const SizedBox(width: 4),
            const Icon(Icons.chevron_right, size: 20),
          ],
        ),
      ),
    );
  }
}
