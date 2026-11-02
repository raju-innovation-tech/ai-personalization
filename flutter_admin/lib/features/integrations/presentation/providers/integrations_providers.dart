import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/integrations_repository.dart';
import '../../domain/integration_status.dart';

final integrationsRepositoryProvider = Provider<IntegrationsRepository>((ref) {
  return IntegrationsRepository(apiClient: ref.watch(apiClientProvider));
});

final integrationStatusProvider = FutureProvider.autoDispose<IntegrationStatus>((ref) async {
  return ref.watch(integrationsRepositoryProvider).fetchStatus();
});
