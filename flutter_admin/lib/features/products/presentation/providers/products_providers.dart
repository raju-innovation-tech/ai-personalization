import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/products_repository.dart';
import '../../domain/product.dart';

final productsRepositoryProvider = Provider<ProductsRepository>((ref) {
  return ProductsRepository(apiClient: ref.watch(apiClientProvider));
});

final productQueryProvider = StateProvider<ProductQuery>((ref) => const ProductQuery());

final productsPageProvider = FutureProvider.autoDispose<ProductPage>((ref) async {
  final query = ref.watch(productQueryProvider);
  return ref.watch(productsRepositoryProvider).fetchPage(query);
});

final productFiltersProvider = FutureProvider.autoDispose<ProductFilters>((ref) async {
  return ref.watch(productsRepositoryProvider).fetchFilters();
});
