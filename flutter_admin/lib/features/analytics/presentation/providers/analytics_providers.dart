import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/analytics_repository.dart';
import '../../domain/report.dart';

final analyticsRepositoryProvider = Provider<AnalyticsRepository>((ref) {
  return AnalyticsRepository(apiClient: ref.watch(apiClientProvider));
});

/// Length of the analytics period in days (7, 14, 30 or 90).
final analyticsDaysProvider = StateProvider<int>((ref) => 30);

final analyticsReportProvider = FutureProvider.autoDispose<AnalyticsReport>((ref) async {
  final days = ref.watch(analyticsDaysProvider);
  return ref.watch(analyticsRepositoryProvider).fetchReport(days);
});
