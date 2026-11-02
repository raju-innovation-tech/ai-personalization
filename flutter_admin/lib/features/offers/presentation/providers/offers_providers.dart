import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/offers_repository.dart';
import '../../domain/offer.dart';

final offersRepositoryProvider = Provider<OffersRepository>((ref) {
  return OffersRepository(apiClient: ref.watch(apiClientProvider));
});

final offerQueryProvider = StateProvider<OfferQuery>((ref) => const OfferQuery());

final offersPageProvider = FutureProvider.autoDispose<OfferPage>((ref) async {
  final query = ref.watch(offerQueryProvider);
  return ref.watch(offersRepositoryProvider).fetchPage(query);
});

final offerTotalsProvider = FutureProvider.autoDispose<OfferTotals>((ref) async {
  return ref.watch(offersRepositoryProvider).fetchTotals();
});

/// Offers the engine would show this customer right now (customer detail page).
final customerOffersProvider =
    FutureProvider.autoDispose.family<List<OfferSuggestion>, String>((ref, userId) async {
  return ref.watch(offersRepositoryProvider).forUser(userId, limit: 5);
});
