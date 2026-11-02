import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/dashboard_repository.dart';
import '../../domain/overview.dart';
import '../../domain/system_health.dart';

final dashboardRepositoryProvider = Provider<DashboardRepository>((ref) {
  return DashboardRepository(apiClient: ref.watch(apiClientProvider));
});

final systemHealthProvider = FutureProvider.autoDispose<SystemHealthStatus>((ref) async {
  final repository = ref.watch(dashboardRepositoryProvider);
  return repository.fetchSystemHealth();
});

final dashboardOverviewProvider = FutureProvider.autoDispose<DashboardOverview>((ref) async {
  final repository = ref.watch(dashboardRepositoryProvider);
  return repository.fetchOverview();
});
