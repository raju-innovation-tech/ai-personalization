import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/recommendations_repository.dart';
import '../../domain/recommendation.dart';

final recommendationsRepositoryProvider = Provider<RecommendationsRepository>((ref) {
  return RecommendationsRepository(apiClient: ref.watch(apiClientProvider));
});

final recommendationStatusProvider = FutureProvider.autoDispose<EngineStatus>((ref) async {
  return ref.watch(recommendationsRepositoryProvider).status();
});

final similarProductsProvider =
    FutureProvider.autoDispose.family<RecommendationResult, String>((ref, productId) async {
  return ref.watch(recommendationsRepositoryProvider).similar(productId);
});

final boughtTogetherProvider =
    FutureProvider.autoDispose.family<RecommendationResult, String>((ref, productId) async {
  return ref.watch(recommendationsRepositoryProvider).frequentlyBought(productId);
});

final userRecommendationsProvider =
    FutureProvider.autoDispose.family<RecommendationResult, String>((ref, userId) async {
  return ref.watch(recommendationsRepositoryProvider).forUser(userId, limit: 5);
});
