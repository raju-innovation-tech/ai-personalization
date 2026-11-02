import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../offers/domain/offer.dart';
import '../../../offers/presentation/providers/offers_providers.dart';
import '../../../products/domain/product.dart';
import '../../../products/presentation/providers/products_providers.dart';
import '../../domain/search_results.dart';
import '../providers/search_providers.dart';

void showSearchDialog(BuildContext context) {
  showDialog<void>(context: context, builder: (_) => const SearchDialog());
}

/// The fake "search box" shown in the desktop top bar; tapping it opens the real search dialog.
class SearchBarButton extends StatelessWidget {
  const SearchBarButton({super.key});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: () => showSearchDialog(context),
      child: Container(
        height: 40,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: isDark ? AppColors.borderDark : AppColors.borderLight),
        ),
        child: Row(
          children: [
            const Icon(Icons.search, size: 20),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Search customers, products, offers...',
                style: Theme.of(context).textTheme.bodyMedium,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Search icon for the mobile app bar.
class SearchIconButton extends StatelessWidget {
  const SearchIconButton({super.key});

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: 'Search',
      icon: const Icon(Icons.search),
      onPressed: () => showSearchDialog(context),
    );
  }
}

class SearchDialog extends ConsumerStatefulWidget {
  const SearchDialog({super.key});

  @override
  ConsumerState<SearchDialog> createState() => _SearchDialogState();
}

class _SearchDialogState extends ConsumerState<SearchDialog> {
  final TextEditingController _controller = TextEditingController();
  Timer? _debounce;
  Future<SearchResults>? _future;
  String _query = '';

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      if (!mounted) return;
      final trimmed = value.trim();
      setState(() {
        _query = trimmed;
        _future = trimmed.length >= 2 ? ref.read(searchRepositoryProvider).search(trimmed) : null;
      });
    });
  }

  /// Close the dialog first, then navigate (the router is looked up before the dialog's context goes away).
  void _open(void Function(GoRouter router) navigate) {
    final router = GoRouter.of(context);
    Navigator.of(context).pop();
    navigate(router);
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Dialog(
      alignment: Alignment.topCenter,
      insetPadding: const EdgeInsets.fromLTRB(16, 72, 16, 16),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560, maxHeight: 520),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: _controller,
                autofocus: true,
                onChanged: _onChanged,
                decoration: InputDecoration(
                  hintText: 'Search customers, products, offers...',
                  prefixIcon: const Icon(Icons.search),
                  suffixIcon: IconButton(
                    tooltip: 'Close',
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Flexible(
                child: _future == null
                    ? Padding(
                        padding: const EdgeInsets.all(12),
                        child: Text(
                          _query.isEmpty ? 'Type at least 2 characters.' : 'Keep typing...',
                          style: textTheme.bodyMedium,
                        ),
                      )
                    : FutureBuilder<SearchResults>(
                        future: _future,
                        builder: (context, snapshot) {
                          if (snapshot.connectionState != ConnectionState.done) {
                            return const Padding(
                              padding: EdgeInsets.all(24),
                              child: Center(child: CircularProgressIndicator(strokeWidth: 2.5)),
                            );
                          }
                          if (snapshot.hasError) {
                            return Padding(
                              padding: const EdgeInsets.all(12),
                              child: Text(errorMessageOf(snapshot.error!), style: textTheme.bodyMedium),
                            );
                          }
                          final results = snapshot.data!;
                          if (results.isEmpty) {
                            return Padding(
                              padding: const EdgeInsets.all(12),
                              child: Text('Nothing found for "$_query".', style: textTheme.bodyMedium),
                            );
                          }
                          return _Results(results: results, onOpen: _open);
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Results extends ConsumerWidget {
  const _Results({required this.results, required this.onOpen});

  final SearchResults results;
  final void Function(void Function(GoRouter router) navigate) onOpen;

  Widget _header(BuildContext context, String text) => Padding(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
        child: Text(text, style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
      );

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      shrinkWrap: true,
      children: [
        if (results.customers.isNotEmpty) ...[
          _header(context, 'Customers'),
          for (final customer in results.customers)
            ListTile(
              dense: true,
              leading: const Icon(Icons.person_outline),
              title: Text(customer.id),
              subtitle: customer.segment == null ? null : Text(customer.segment!),
              onTap: () => onOpen((router) => router.go('/customers/${Uri.encodeComponent(customer.id)}')),
            ),
        ],
        if (results.products.isNotEmpty) ...[
          _header(context, 'Products'),
          for (final product in results.products)
            ListTile(
              dense: true,
              leading: const Icon(Icons.inventory_2_outlined),
              title: Text(product.name, overflow: TextOverflow.ellipsis),
              subtitle: Text([product.id, if (product.category != null) product.category!].join(' • ')),
              onTap: () {
                ref.read(productQueryProvider.notifier).state = const ProductQuery().copyWith(search: product.id);
                onOpen((router) => router.go('/products'));
              },
            ),
        ],
        if (results.offers.isNotEmpty) ...[
          _header(context, 'Offers'),
          for (final offer in results.offers)
            ListTile(
              dense: true,
              leading: const Icon(Icons.local_offer_outlined),
              title: Text(offer.name, overflow: TextOverflow.ellipsis),
              subtitle: Text('${offer.code} • ${humanize(offer.status)}'),
              onTap: () {
                ref.read(offerQueryProvider.notifier).state = const OfferQuery().copyWith(search: offer.code);
                onOpen((router) => router.go('/offers'));
              },
            ),
        ],
      ],
    );
  }
}
