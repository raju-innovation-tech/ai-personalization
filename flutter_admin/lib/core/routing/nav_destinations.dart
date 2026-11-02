import 'package:flutter/material.dart';

class NavDestination {
  const NavDestination({
    required this.label,
    required this.icon,
    required this.path,
    this.adminOnly = false,
    this.children = const [],
  });

  final String label;
  final IconData icon;
  final String path;

  /// Hidden from the sidebar for non-admins (the API enforces this too).
  final bool adminOnly;
  final List<NavDestination> children;
}

/// Sidebar structure per project spec (§39 — Admin Navigation).
/// Everything is live (Phases 1-5) except Experiments (A/B testing, Phase 6),
/// which renders a "coming in a later phase" screen.
const List<NavDestination> appNavDestinations = [
  NavDestination(label: 'Dashboard', icon: Icons.dashboard_outlined, path: '/dashboard'),
  NavDestination(label: 'Customers', icon: Icons.people_outline, path: '/customers'),
  NavDestination(label: 'Segments', icon: Icons.donut_small_outlined, path: '/segments'),
  NavDestination(label: 'Products', icon: Icons.inventory_2_outlined, path: '/products'),
  NavDestination(label: 'Recommendations', icon: Icons.auto_awesome_outlined, path: '/recommendations'),
  NavDestination(label: 'Offers', icon: Icons.local_offer_outlined, path: '/offers'),
  NavDestination(label: 'Experiments', icon: Icons.science_outlined, path: '/experiments'),
  NavDestination(label: 'ML Insights', icon: Icons.psychology_rounded, path: '/ml'),
  NavDestination(label: 'Analytics', icon: Icons.bar_chart_outlined, path: '/analytics'),
  NavDestination(label: 'Integrations', icon: Icons.hub_outlined, path: '/integrations'),
  NavDestination(label: 'Users', icon: Icons.manage_accounts_outlined, path: '/users', adminOnly: true),
  NavDestination(label: 'System', icon: Icons.settings_outlined, path: '/system', adminOnly: true),
];

/// The sidebar entries this person may see.
List<NavDestination> visibleDestinations({required bool isAdmin}) {
  return appNavDestinations.where((d) => isAdmin || !d.adminOnly).toList();
}
