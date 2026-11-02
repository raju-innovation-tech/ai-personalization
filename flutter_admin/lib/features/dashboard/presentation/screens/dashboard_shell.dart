import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/routing/nav_destinations.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/responsive.dart';
import '../../../../core/widgets/server_config_dialog.dart';
import '../../../../core/widgets/theme_toggle_button.dart';
import '../../../auth/domain/admin_user.dart';
import '../../../auth/presentation/providers/auth_controller.dart';
import '../../../auth/presentation/providers/auth_state.dart';
import '../../../search/presentation/widgets/search_dialog.dart';
import '../../../system_health/presentation/widgets/alerts_button.dart';

/// Modern, fully responsive DashboardShell supporting mobile, tablet, laptop, and ultra-wide screens.
class DashboardShell extends ConsumerStatefulWidget {
  const DashboardShell({super.key, required this.child, required this.currentPath});

  final Widget child;
  final String currentPath;

  @override
  ConsumerState<DashboardShell> createState() => _DashboardShellState();
}

class _DashboardShellState extends ConsumerState<DashboardShell> {
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  bool _sidebarCollapsedOverride = false;

  @override
  Widget build(BuildContext context) {
    final isDesktop = Responsive.isDesktop(context);
    final isTablet = Responsive.isTablet(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final shouldCollapse = isTablet || _sidebarCollapsedOverride;

    if (isDesktop || isTablet) {
      return Scaffold(
        key: _scaffoldKey,
        body: Row(
          children: [
            _Sidebar(
              currentPath: widget.currentPath,
              collapsed: shouldCollapse,
              onToggleCollapse: () {
                setState(() {
                  _sidebarCollapsedOverride = !_sidebarCollapsedOverride;
                });
              },
            ),
            Expanded(
              child: Column(
                children: [
                  _TopBar(
                    showMenuButton: false,
                    currentPath: widget.currentPath,
                    isCollapsed: shouldCollapse,
                    onToggleCollapse: () {
                      setState(() {
                        _sidebarCollapsedOverride = !_sidebarCollapsedOverride;
                      });
                    },
                  ),
                  Expanded(
                    child: Container(
                      color: isDark ? AppColors.backgroundDark : AppColors.backgroundLight,
                      child: SafeArea(
                        top: false,
                        child: Padding(
                          padding: Responsive.contentPadding(context),
                          child: widget.child,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
    }

    // Mobile Layout: modern AppBar + Drawer + Bottom Navigation Bar
    final selectedNavIndex = _mobileNavIndex(widget.currentPath);

    return Scaffold(
      key: _scaffoldKey,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.menu_rounded, size: 24),
          tooltip: 'Navigation Menu',
          onPressed: () => _scaffoldKey.currentState?.openDrawer(),
        ),
        title: Text(
          _titleForPath(widget.currentPath),
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18),
        ),
        actions: [
          IconButton(
            tooltip: 'Server Connection',
            icon: const Icon(Icons.dns_outlined, size: 20),
            onPressed: () => showServerConfigDialog(context),
          ),
          const SearchIconButton(),
          const ThemeToggleButton(),
          const SizedBox(width: 4),
        ],
      ),
      drawer: Drawer(
        backgroundColor: isDark ? AppColors.cardDark : AppColors.cardLight,
        child: _Sidebar(
          currentPath: widget.currentPath,
          collapsed: false,
          isDrawer: true,
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedNavIndex,
        height: 64,
        elevation: 2,
        backgroundColor: isDark ? AppColors.cardDark : AppColors.cardLight,
        indicatorColor: AppColors.primary.withValues(alpha: 0.15),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard_rounded, color: AppColors.primary),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.people_outline),
            selectedIcon: Icon(Icons.people_rounded, color: AppColors.primary),
            label: 'Customers',
          ),
          NavigationDestination(
            icon: Icon(Icons.auto_awesome_outlined),
            selectedIcon: Icon(Icons.auto_awesome_rounded, color: AppColors.primary),
            label: 'Recs',
          ),
          NavigationDestination(
            icon: Icon(Icons.local_offer_outlined),
            selectedIcon: Icon(Icons.local_offer_rounded, color: AppColors.primary),
            label: 'Offers',
          ),
          NavigationDestination(
            icon: Icon(Icons.apps_rounded),
            selectedIcon: Icon(Icons.apps_rounded, color: AppColors.primary),
            label: 'Menu',
          ),
        ],
        onDestinationSelected: (index) {
          switch (index) {
            case 0:
              context.go('/dashboard');
              break;
            case 1:
              context.go('/customers');
              break;
            case 2:
              context.go('/recommendations');
              break;
            case 3:
              context.go('/offers');
              break;
            case 4:
              _scaffoldKey.currentState?.openDrawer();
              break;
          }
        },
      ),
      body: SafeArea(
        child: Padding(
          padding: Responsive.contentPadding(context),
          child: widget.child,
        ),
      ),
    );
  }

  int _mobileNavIndex(String path) {
    if (path.startsWith('/dashboard')) return 0;
    if (path.startsWith('/customers')) return 1;
    if (path.startsWith('/recommendations')) return 2;
    if (path.startsWith('/offers')) return 3;
    return 4; // Highlight 'Menu' for other paths
  }

  String _titleForPath(String path) {
    return appNavDestinations
        .firstWhere((d) => path.startsWith(d.path), orElse: () => appNavDestinations.first)
        .label;
  }
}

class _Sidebar extends ConsumerWidget {
  const _Sidebar({
    required this.currentPath,
    required this.collapsed,
    this.isDrawer = false,
    this.onToggleCollapse,
  });

  final String currentPath;
  final bool collapsed;
  final bool isDrawer;
  final VoidCallback? onToggleCollapse;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final authState = ref.watch(authControllerProvider);
    final userName = authState is AuthAuthenticated ? authState.user.fullName : 'Admin User';
    final userRole = authState is AuthAuthenticated ? authState.user.role.displayName : 'Staff';
    final isAdmin = authState is AuthAuthenticated &&
        (authState.user.role == UserRole.superAdmin || authState.user.role == UserRole.admin);

    final avatar = Container(
      width: 36,
      height: 36,
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppColors.primary, AppColors.accentPurple],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Center(
        child: Text(
          userName.isNotEmpty ? userName[0].toUpperCase() : 'A',
          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 16),
        ),
      ),
    );

    return Container(
      width: collapsed ? 76 : (isDrawer ? null : 260),
      decoration: BoxDecoration(
        color: isDark ? AppColors.cardDark : AppColors.cardLight,
        border: Border(
          right: BorderSide(
            color: isDark ? AppColors.borderDark : AppColors.borderLight,
            width: 1,
          ),
        ),
      ),
      child: SafeArea(
        child: Column(
          children: [
            // Header: Brand & Live Engine Badge
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
              child: Row(
                children: [
                  Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        colors: [AppColors.primary, AppColors.accentCyan],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      borderRadius: BorderRadius.circular(12),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.primary.withValues(alpha: 0.35),
                          blurRadius: 10,
                          offset: const Offset(0, 3),
                        ),
                      ],
                    ),
                    child: const Icon(Icons.insights_rounded, color: Colors.white, size: 22),
                  ),
                  if (!collapsed) ...[
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'AI Personalization',
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: -0.2,
                                ),
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 2),
                          Row(
                            children: [
                              Container(
                                width: 6,
                                height: 6,
                                decoration: const BoxDecoration(
                                  color: AppColors.success,
                                  shape: BoxShape.circle,
                                ),
                              ),
                              const SizedBox(width: 5),
                              Text(
                                'Engine Live (8 Phases)',
                                style: TextStyle(
                                  color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
            Divider(
              height: 1,
              color: isDark ? AppColors.borderDark : AppColors.borderLight,
            ),

            // Navigation List
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(vertical: 10),
                children: [
                  if (!collapsed)
                    _NavGroupHeader(title: 'MAIN CORE', isDark: isDark),
                  ...visibleDestinations(isAdmin: isAdmin).sublist(0, 4).map((d) {
                    final selected = currentPath.startsWith(d.path);
                    return _SidebarItem(destination: d, selected: selected, collapsed: collapsed);
                  }),
                  if (!collapsed)
                    _NavGroupHeader(title: 'INTELLIGENCE & ML', isDark: isDark),
                  ...visibleDestinations(isAdmin: isAdmin).sublist(4, 8).map((d) {
                    final selected = currentPath.startsWith(d.path);
                    return _SidebarItem(destination: d, selected: selected, collapsed: collapsed);
                  }),
                  if (!collapsed)
                    _NavGroupHeader(title: 'OPS & CONFIGURATION', isDark: isDark),
                  ...visibleDestinations(isAdmin: isAdmin).sublist(8).map((d) {
                    final selected = currentPath.startsWith(d.path);
                    return _SidebarItem(destination: d, selected: selected, collapsed: collapsed);
                  }),
                ],
              ),
            ),

            Divider(
              height: 1,
              color: isDark ? AppColors.borderDark : AppColors.borderLight,
            ),

            // User Info & Footer
            Padding(
              padding: const EdgeInsets.all(12),
              child: collapsed
                  ? Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        avatar,
                        const SizedBox(height: 6),
                        IconButton(
                          tooltip: 'Server Connection',
                          icon: const Icon(Icons.dns_outlined, size: 20),
                          onPressed: () => showServerConfigDialog(context),
                        ),
                        IconButton(
                          tooltip: 'Logout',
                          icon: const Icon(Icons.logout_rounded, size: 20),
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
                              Text(
                                userName,
                                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                      fontWeight: FontWeight.w700,
                                    ),
                                overflow: TextOverflow.ellipsis,
                              ),
                              Row(
                                children: [
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: AppColors.primary.withValues(alpha: 0.12),
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Text(
                                      userRole,
                                      style: const TextStyle(
                                        color: AppColors.primary,
                                        fontSize: 10,
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                        IconButton(
                          tooltip: 'Server Connection',
                          icon: const Icon(Icons.dns_outlined, size: 20),
                          onPressed: () => showServerConfigDialog(context),
                        ),
                        IconButton(
                          tooltip: 'Logout',
                          icon: const Icon(Icons.logout_rounded, size: 20),
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

class _NavGroupHeader extends StatelessWidget {
  const _NavGroupHeader({required this.title, required this.isDark});

  final String title;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 18, right: 18, top: 14, bottom: 6),
      child: Text(
        title,
        style: TextStyle(
          color: isDark ? AppColors.textTertiaryDark : AppColors.textTertiaryLight,
          fontSize: 11,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.8,
        ),
      ),
    );
  }
}

class _SidebarItem extends StatelessWidget {
  const _SidebarItem({
    required this.destination,
    required this.selected,
    required this.collapsed,
  });

  final NavDestination destination;
  final bool selected;
  final bool collapsed;

  void _navigate(BuildContext context) {
    Scaffold.maybeOf(context)?.closeDrawer();
    context.go(destination.path);
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final color = selected
        ? (isDark ? Colors.white : AppColors.primaryDark)
        : (isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight);

    final bgGradient = selected
        ? LinearGradient(
            colors: [
              AppColors.primary.withValues(alpha: isDark ? 0.25 : 0.14),
              AppColors.primary.withValues(alpha: isDark ? 0.08 : 0.04),
            ],
            begin: Alignment.centerLeft,
            end: Alignment.centerRight,
          )
        : null;

    if (collapsed) {
      return Tooltip(
        message: destination.label,
        waitDuration: const Duration(milliseconds: 250),
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
          decoration: BoxDecoration(
            gradient: bgGradient,
            borderRadius: BorderRadius.circular(10),
            border: selected
                ? Border.all(color: AppColors.primary.withValues(alpha: 0.35))
                : null,
          ),
          child: InkWell(
            borderRadius: BorderRadius.circular(10),
            onTap: () => _navigate(context),
            child: SizedBox(
              height: 44,
              child: Center(
                child: Icon(
                  destination.icon,
                  color: selected ? AppColors.primary : color,
                  size: 22,
                ),
              ),
            ),
          ),
        ),
      );
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
      decoration: BoxDecoration(
        gradient: bgGradient,
        borderRadius: BorderRadius.circular(10),
        border: selected
            ? Border.all(color: AppColors.primary.withValues(alpha: 0.3))
            : null,
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(10),
        child: ListTile(
          dense: true,
          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
          leading: Icon(
            destination.icon,
            color: selected ? AppColors.primary : color,
            size: 20,
          ),
          title: Text(
            destination.label,
            style: TextStyle(
              color: color,
              fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
              fontSize: 13.5,
            ),
          ),
          trailing: selected
              ? Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(
                    color: AppColors.primary,
                    shape: BoxShape.circle,
                  ),
                )
              : null,
          onTap: () => _navigate(context),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget implements PreferredSizeWidget {
  const _TopBar({
    required this.showMenuButton,
    required this.currentPath,
    required this.isCollapsed,
    this.onToggleCollapse,
  });

  final bool showMenuButton;
  final String currentPath;
  final bool isCollapsed;
  final VoidCallback? onToggleCollapse;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      height: 64,
      padding: const EdgeInsets.symmetric(horizontal: 20),
      decoration: BoxDecoration(
        color: isDark ? AppColors.backgroundDark : AppColors.backgroundLight,
        border: Border(
          bottom: BorderSide(
            color: isDark ? AppColors.borderDark : AppColors.borderLight,
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          if (onToggleCollapse != null)
            IconButton(
              icon: Icon(
                isCollapsed ? Icons.menu_open_rounded : Icons.menu_rounded,
                size: 20,
                color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
              ),
              tooltip: isCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar',
              onPressed: onToggleCollapse,
            ),
          const SizedBox(width: 8),
          Expanded(
            child: Align(
              alignment: Alignment.centerLeft,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 440),
                child: const SearchBarButton(),
              ),
            ),
          ),
          const SizedBox(width: 16),
          // Live Store Connection Pill
          Tooltip(
            message: 'Server Connection & Endpoint Settings',
            child: InkWell(
              borderRadius: BorderRadius.circular(20),
              onTap: () => showServerConfigDialog(context),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: AppColors.success.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: AppColors.success.withValues(alpha: 0.3)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 7,
                      height: 7,
                      decoration: const BoxDecoration(
                        color: AppColors.success,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    const Text(
                      'Welfog Store Connected',
                      style: TextStyle(
                        color: AppColors.success,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          const AlertsButton(),
          const ThemeToggleButton(),
        ],
      ),
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(64);
}
