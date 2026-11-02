import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/system_repository.dart';
import '../../domain/system.dart';

final systemRepositoryProvider = Provider<SystemRepository>((ref) {
  return SystemRepository(apiClient: ref.watch(apiClientProvider));
});

final systemStatusProvider = FutureProvider.autoDispose<SystemStatus>((ref) async {
  return ref.watch(systemRepositoryProvider).fetchStatus();
});

/// Alerts for the notification bell: loaded immediately, then refreshed every 2 minutes.
final systemAlertsProvider = StreamProvider.autoDispose<AlertsResult>((ref) async* {
  final repository = ref.watch(systemRepositoryProvider);
  yield await repository.fetchAlerts();
  yield* Stream<void>.periodic(const Duration(minutes: 2)).asyncMap((_) => repository.fetchAlerts());
});
