import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/ml_repository.dart';
import '../../domain/ml_models.dart';

final mlRepositoryProvider = Provider<MlRepository>((ref) {
  return MlRepository(apiClient: ref.watch(apiClientProvider));
});

final mlModelsProvider = FutureProvider.autoDispose<List<MlModelInfo>>((ref) async {
  return ref.watch(mlRepositoryProvider).fetchModels();
});

final mlTopChurnProvider = FutureProvider.autoDispose<List<TopRiskCustomer>>((ref) async {
  return ref.watch(mlRepositoryProvider).fetchTopChurnRisks(limit: 25, minScore: 0.4);
});

final mlTopPurchaseProvider = FutureProvider.autoDispose<List<TopRiskCustomer>>((ref) async {
  return ref.watch(mlRepositoryProvider).fetchTopPurchaseProbability(limit: 25, minScore: 0.4);
});

final mlChurnDistributionProvider =
    FutureProvider.autoDispose<ScoreDistribution>((ref) async {
  return ref.watch(mlRepositoryProvider).fetchDistribution('churn');
});

final mlPurchaseDistributionProvider =
    FutureProvider.autoDispose<ScoreDistribution>((ref) async {
  return ref.watch(mlRepositoryProvider).fetchDistribution('purchase');
});

/// Triggered manually by the "Rebuild Models" button.
final mlRebuildProvider = FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  return ref.watch(mlRepositoryProvider).rebuild();
});

/// Per-customer profile (purchase + churn + offer).
final mlCustomerProfileProvider =
    FutureProvider.autoDispose.family<CustomerMlProfile?, String>((ref, userId) async {
  return ref.watch(mlRepositoryProvider).fetchCustomerProfile(userId);
});
