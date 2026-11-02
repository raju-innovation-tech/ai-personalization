import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/analytics/presentation/screens/analytics_screen.dart';
import '../../features/auth/presentation/providers/auth_controller.dart';
import '../../features/auth/presentation/providers/auth_state.dart';
import '../../features/auth/presentation/screens/login_screen.dart';
import '../../features/customers/presentation/screens/customer_detail_screen.dart';
import '../../features/customers/presentation/screens/customers_screen.dart';
import '../../features/dashboard/presentation/screens/dashboard_screen.dart';
import '../../features/dashboard/presentation/screens/dashboard_shell.dart';
import '../../features/experiments/presentation/screens/experiment_detail_screen.dart';
import '../../features/experiments/presentation/screens/experiments_screen.dart';
import '../../features/integrations/presentation/screens/integrations_screen.dart';
import '../../features/offers/presentation/screens/offers_screen.dart';
import '../../features/products/presentation/screens/products_screen.dart';
import '../../features/recommendations/presentation/screens/recommendations_screen.dart';
import '../../features/segments/presentation/screens/segments_screen.dart';
import '../../features/system_health/presentation/screens/system_screen.dart';
import '../../features/users/presentation/screens/users_screen.dart';
import '../../features/models/presentation/screens/ml_insights_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/dashboard',
    refreshListenable: _AuthStateListenable(ref),
    redirect: (context, state) {
      final authState = ref.read(authControllerProvider);
      final isLoggingIn = state.matchedLocation == '/login';

      if (authState is AuthInitial || authState is AuthLoading) {
        return null; // stay put while session restore / login is in flight
      }

      final isAuthenticated = authState is AuthAuthenticated;

      if (!isAuthenticated && !isLoggingIn) return '/login';
      if (isAuthenticated && isLoggingIn) return '/dashboard';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      ShellRoute(
        builder: (context, state, child) {
          return DashboardShell(currentPath: state.matchedLocation, child: child);
        },
        routes: [
          GoRoute(path: '/dashboard', builder: (context, state) => const DashboardScreen()),
          GoRoute(path: '/customers', builder: (context, state) => const CustomersScreen()),
          GoRoute(
            path: '/customers/:id',
            builder: (context, state) => CustomerDetailScreen(
              key: ValueKey(state.pathParameters['id']),
              customerId: state.pathParameters['id'] ?? '',
            ),
          ),
          GoRoute(path: '/segments', builder: (context, state) => const SegmentsScreen()),
          GoRoute(path: '/products', builder: (context, state) => const ProductsScreen()),
          GoRoute(path: '/recommendations', builder: (context, state) => const RecommendationsScreen()),
          GoRoute(path: '/offers', builder: (context, state) => const OffersScreen()),
          GoRoute(path: '/experiments', builder: (context, state) => const ExperimentsScreen()),
          GoRoute(
            path: '/experiments/:id',
            builder: (context, state) => ExperimentDetailScreen(
              key: ValueKey(state.pathParameters['id']),
              experimentId: state.pathParameters['id'] ?? '',
            ),
          ),
          GoRoute(path: '/analytics', builder: (context, state) => const AnalyticsScreen()),
          GoRoute(path: '/integrations', builder: (context, state) => const IntegrationsScreen()),
          GoRoute(path: '/users', builder: (context, state) => const UsersScreen()),
          GoRoute(path: '/system', builder: (context, state) => const SystemScreen()),
          GoRoute(path: '/ml', builder: (context, state) => const MlInsightsScreen()),
        ],
      ),
    ],
  );
});

/// Bridges Riverpod's StateNotifier to GoRouter's Listenable-based
/// refresh mechanism, so navigation redirects re-evaluate on auth changes.
class _AuthStateListenable extends ChangeNotifier {
  _AuthStateListenable(this._ref) {
    _ref.listen(authControllerProvider, (_, __) => notifyListeners());
  }

  final Ref _ref;
}
