import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../domain/product.dart';
import '../providers/products_providers.dart';
import '../widgets/product_detail_dialog.dart';

class ProductsScreen extends ConsumerStatefulWidget {
  const ProductsScreen({super.key});

  @override
  ConsumerState<ProductsScreen> createState() => _ProductsScreenState();
}

class _ProductsScreenState extends ConsumerState<ProductsScreen> {
  final TextEditingController _searchController = TextEditingController();
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    // The global search (or a previous visit) may already have set a search text.
    _searchController.text = ref.read(productQueryProvider).search;
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  void _onSearchChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 400), () {
      if (!mounted) return;
      final query = ref.read(productQueryProvider);
      ref.read(productQueryProvider.notifier).state = query.copyWith(search: value);
    });
  }

  void _update(ProductQuery Function(ProductQuery current) change) {
    ref.read(productQueryProvider.notifier).state = change(ref.read(productQueryProvider));
  }

  String _sortKey(ProductQuery query) {
    if (query.sort == 'price') return query.descending ? 'price_desc' : 'price_asc';
    if (query.sort == 'rating') return 'rating';
    return 'name';
  }

  void _onSortChanged(String? key) {
    switch (key) {
      case 'price_asc':
        _update((q) => q.copyWith(sort: 'price', descending: false));
      case 'price_desc':
        _update((q) => q.copyWith(sort: 'price', descending: true));
      case 'rating':
        _update((q) => q.copyWith(sort: 'rating', descending: true));
      default:
        _update((q) => q.copyWith(sort: 'name', descending: false));
    }
  }

  @override
  Widget build(BuildContext context) {
    final query = ref.watch(productQueryProvider);
    final pageAsync = ref.watch(productsPageProvider);
    final categories = ref.watch(productFiltersProvider).valueOrNull?.categories ?? const <String>[];
    final selectedCategory = (query.category != null && categories.contains(query.category)) ? query.category : null;
    final textTheme = Theme.of(context).textTheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Products', style: textTheme.headlineSmall),
        const SizedBox(height: 4),
        Text('Catalog synced from your store. Tap a product to see its recommendations.',
            style: textTheme.bodyMedium),
        const SizedBox(height: 16),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 300,
              child: TextField(
                controller: _searchController,
                onChanged: _onSearchChanged,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  hintText: 'Search name, SKU or brand',
                  isDense: true,
                ),
              ),
            ),
            SizedBox(
              width: 220,
              child: InputDecorator(
                decoration: const InputDecoration(
                  labelText: 'Category',
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String?>(
                    isExpanded: true,
                    isDense: true,
                    value: selectedCategory,
                    items: [
                      const DropdownMenuItem<String?>(value: null, child: Text('All categories')),
                      for (final category in categories)
                        DropdownMenuItem<String?>(value: category, child: Text(category, overflow: TextOverflow.ellipsis)),
                    ],
                    onChanged: (value) => _update(
                      (q) => value == null ? q.copyWith(clearCategory: true) : q.copyWith(category: value),
                    ),
                  ),
                ),
              ),
            ),
            SizedBox(
              width: 200,
              child: InputDecorator(
                decoration: const InputDecoration(
                  labelText: 'Sort by',
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    isExpanded: true,
                    isDense: true,
                    value: _sortKey(query),
                    items: const [
                      DropdownMenuItem(value: 'name', child: Text('Name (A–Z)')),
                      DropdownMenuItem(value: 'price_asc', child: Text('Price: low to high')),
                      DropdownMenuItem(value: 'price_desc', child: Text('Price: high to low')),
                      DropdownMenuItem(value: 'rating', child: Text('Top rated')),
                    ],
                    onChanged: _onSortChanged,
                  ),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Expanded(
          child: pageAsync.when(
            loading: () => const LoadingState(message: 'Loading products...'),
            error: (error, _) => ErrorState(
              message: errorMessageOf(error),
              onRetry: () => ref.invalidate(productsPageProvider),
            ),
            data: (page) {
              if (page.items.isEmpty) {
                return const EmptyState(
                  title: 'No products found',
                  subtitle: 'Try a different search or filter.',
                  icon: Icons.search_off,
                );
              }
              return Column(
                children: [
                  Expanded(
                    child: Card(
                      clipBehavior: Clip.antiAlias,
                      child: ListView.separated(
                        itemCount: page.items.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (context, index) => _ProductRow(product: page.items[index]),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  _Pager(
                    page: page,
                    onPage: (target) => _update((q) => q.copyWith(page: target)),
                  ),
                ],
              );
            },
          ),
        ),
      ],
    );
  }
}

class _ProductRow extends StatelessWidget {
  const _ProductRow({required this.product});

  final Product product;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final meta = [product.category, product.brand, product.productId].whereType<String>().join(' • ');
    final initial = (product.category ?? product.name).isNotEmpty ? (product.category ?? product.name)[0] : '?';

    return InkWell(
      onTap: () => showDialog<void>(
        context: context,
        builder: (_) => ProductDetailDialog(product: product),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            CircleAvatar(
              radius: 20,
              backgroundColor: AppColors.primary.withValues(alpha: 0.12),
              child: Text(initial.toUpperCase(), style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(product.name, style: textTheme.titleMedium?.copyWith(fontSize: 14), maxLines: 1, overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 2),
                  Text(meta, style: textTheme.bodyMedium?.copyWith(fontSize: 12), maxLines: 1, overflow: TextOverflow.ellipsis),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(formatPrice(product.price), style: textTheme.titleMedium?.copyWith(fontSize: 14)),
                const SizedBox(height: 4),
                _StockBadge(inStock: product.inStock),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _StockBadge extends StatelessWidget {
  const _StockBadge({required this.inStock});

  final bool inStock;

  @override
  Widget build(BuildContext context) {
    final color = inStock ? AppColors.success : AppColors.danger;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
      child: Text(
        inStock ? 'In stock' : 'Out of stock',
        style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }
}

class _Pager extends StatelessWidget {
  const _Pager({required this.page, required this.onPage});

  final ProductPage page;
  final void Function(int page) onPage;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            '${formatCount(page.total)} products  •  page ${page.page} of ${page.totalPages}',
            style: Theme.of(context).textTheme.bodyMedium,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        IconButton(
          tooltip: 'Previous page',
          icon: const Icon(Icons.chevron_left),
          onPressed: page.page > 1 ? () => onPage(page.page - 1) : null,
        ),
        IconButton(
          tooltip: 'Next page',
          icon: const Icon(Icons.chevron_right),
          onPressed: page.page < page.totalPages ? () => onPage(page.page + 1) : null,
        ),
      ],
    );
  }
}
