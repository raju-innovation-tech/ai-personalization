import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/routing/nav_destinations.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/responsive.dart';
import '../../../../core/widgets/theme_toggle_button.dart';
import '../../../auth/domain/admin_user.dart';
import '../../../auth/presentation/providers/auth_controller.dart';
import '../../../auth/presentation/providers/auth_state.dart';
import '../../../search/presentation/widgets/search_dialog.dart';
import '../../../system_health/presentation/widgets/alerts_button.dart';

/// The persistent app shell: sidebar (desktop/tablet) or drawer (mobile)
/// + top bar, wrapping whichever feature screen GoRouter has routed to.
class DashboardShell extends ConsumerWidget {
  const DashboardShell({super.key, required this.child, required this.currentPath});

  final Widget child;
  final String currentPath;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDesktop = Responsive.isDesktop(context) || Responsive.isTablet(context);

    if (isDesktop) {
      return Scaffold(
        body: Row(
          children: [
            _Sidebar(currentPath: currentPath, collapsed: Responsive.isTablet(context)),
            Expanded(
              child: Column(
                children: [
                  _TopBar(showMenuButton: false),
                  Expanded(child: Container(padding: const EdgeInsets.all(24), child: child)),
                ],
              ),
            ),
          ],
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(_titleForPath(currentPath)),
        actions: const [SearchIconButton(), AlertsButton(), ThemeToggleButton()],
      ),
      drawer: Drawer(child: _Sidebar(currentPath: currentPath, collapsed: false)),
      body: Padding(padding: const EdgeInsets.all(16), child: child),
    );
  }

  String _titleForPath(String path) {
    return appNavDestinations
        .firstWhere((d) => path.startsWith(d.path), orElse: () => appNavDestinations.first)
        .label;
  }
}

class _Sidebar extends ConsumerWidget {
  const _Sidebar({required this.currentPath, required this.collapsed});

  final String currentPath;
  final bool collapsed;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final authState = ref.watch(authControllerProvider);
    final userName = authState is AuthAuthenticated ? authState.user.fullName : '';
    final userRole = authState is AuthAuthenticated ? authState.user.role.displayName : '';
    final isAdmin = authState is AuthAuthenticated &&
        (authState.user.role == UserRole.superAdmin || authState.user.role == UserRole.admin);

    final avatar = CircleAvatar(
      radius: 18,
      backgroundColor: AppColors.primary.withValues(alpha: 0.15),
      child: Text(
        userName.isNotEmpty ? userName[0].toUpperCase() : '?',
        style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700),
      ),
    );

    return Container(
      width: collapsed ? 76 : 260,
      color: isDark ? AppColors.cardDark : AppColors.cardLight,
      child: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(color: AppColors.primary, borderRadius: BorderRadius.circular(10)),
                    child: const Icon(Icons.insights_rounded, color: Colors.white, size: 20),
                  ),
                  if (!collapsed) ...[
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'AI Personalization',
                        style: Theme.of(context).textTheme.titleMedium,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(vertical: 8),
                children: visibleDestinations(isAdmin: isAdmin).map((destination) {
                  final selected = currentPath.startsWith(destination.path);
                  return _SidebarItem(destination: destination, selected: selected, collapsed: collapsed);
                }).toList(),
              ),
            ),
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.all(12),
              child: collapsed
                  ? Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        avatar,
                        const SizedBox(height: 4),
                        IconButton(
                          tooltip: 'Logout',
                          icon: const Icon(Icons.logout, size: 20),
                          onPressed: () => ref.read(authControllerProvider.notifier).logout(),
                        ),
                      ],
                    )
                  : Row(
                      children: [
                        avatar,
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(userName, style: Theme.of(context).textTheme.bodyLarge, overflow: TextOverflow.ellipsis),
                              Text(userRole, style: Theme.of(context).textTheme.bodyMedium, overflow: TextOverflow.ellipsis),
                            ],
                          ),
                        ),
                        IconButton(
                          tooltip: 'Logout',
                          icon: const Icon(Icons.logout, size: 20),
                          onPressed: () => ref.read(authControllerProvider.notifier).logout(),
                        ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SidebarItem extends StatelessWidget {
  const _SidebarItem({required this.destination, required this.selected, required this.collapsed});

  final NavDestination destination;
  final bool selected;
  final bool collapsed;

  void _navigate(BuildContext context) {
    // On mobile the sidebar lives inside a Drawer: close it before navigating.
    Scaffold.maybeOf(context)?.closeDrawer();
    context.go(destination.path);
  }

  @override
  Widget build(BuildContext context) {
    final color = selected ? AppColors.primary : Theme.of(context).textTheme.bodyLarge?.color;
    final background = selected ? AppColors.primary.withValues(alpha: 0.1) : Colors.transparent;

    if (collapsed) {
      // Icon-only rail item. (A ListTile needs ~72px of horizontal padding and
      // overflows inside the 76px-wide collapsed sidebar.)
      return Tooltip(
        message: destination.label,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
          decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(10)),
          child: InkWell(
            borderRadius: BorderRadius.circular(10),
            onTap: () => _navigate(context),
            child: SizedBox(
              height: 44,
              child: Center(child: Icon(destination.icon, color: color, size: 22)),
            ),
          ),
        ),
      );
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
      decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(10)),
      child: ListTile(
        dense: true,
        leading: Icon(destination.icon, color: color, size: 22),
        title: Text(
          destination.label,
          style: TextStyle(color: color, fontWeight: selected ? FontWeight.w600 : FontWeight.w400),
        ),
        onTap: () => _navigate(context),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    );
  }
}

class _TopBar extends StatelessWidget implements PreferredSizeWidget {
  const _TopBar({required this.showMenuButton});

  final bool showMenuButton;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      height: 64,
      padding: const EdgeInsets.symmetric(horizontal: 24),
      decoration: BoxDecoration(
        color: isDark ? AppColors.backgroundDark : AppColors.backgroundLight,
        border: Border(bottom: BorderSide(color: isDark ? AppColors.borderDark : AppColors.borderLight)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Align(
              alignment: Alignment.centerLeft,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: const SearchBarButton(),
              ),
            ),
          ),
          const SizedBox(width: 16),
          const AlertsButton(),
          const ThemeToggleButton(),
        ],
      ),
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(64);
}
