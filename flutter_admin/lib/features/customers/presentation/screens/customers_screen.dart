import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/utils/responsive.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../../segments/domain/segment.dart';
import '../../../segments/presentation/providers/segments_providers.dart';
import '../../../segments/presentation/widgets/recompute_button.dart';
import '../../../segments/presentation/widgets/segment_chip.dart';
import '../../domain/customer.dart';
import '../providers/customers_providers.dart';

class CustomersScreen extends ConsumerStatefulWidget {
  const CustomersScreen({super.key});

  @override
  ConsumerState<CustomersScreen> createState() => _CustomersScreenState();
}

class _CustomersScreenState extends ConsumerState<CustomersScreen> {
  final TextEditingController _searchController = TextEditingController();
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    // Coming back from the Segments page ("View customers") or re-opening the screen.
    _searchController.text = ref.read(customerQueryProvider).search;
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  void _update(CustomerQuery Function(CustomerQuery current) change) {
    ref.read(customerQueryProvider.notifier).state = change(ref.read(customerQueryProvider));
  }

  void _onSearchChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 400), () {
      if (!mounted) return;
      _update((q) => q.copyWith(search: value));
    });
  }

  String _sortKey(CustomerQuery query) {
    if (query.sort == 'spend') return 'spend';
    if (query.sort == 'orders') return 'orders';
    if (query.sort == 'rfm') return 'rfm';
    if (query.sort == 'recency') return 'recency';
    return 'last_seen';
  }

  void _onSortChanged(String? key) {
    switch (key) {
      case 'spend':
        _update((q) => q.copyWith(sort: 'spend', descending: true));
      case 'orders':
        _update((q) => q.copyWith(sort: 'orders', descending: true));
      case 'rfm':
        _update((q) => q.copyWith(sort: 'rfm', descending: true));
      case 'recency':
        _update((q) => q.copyWith(sort: 'recency', descending: true));
      default:
        _update((q) => q.copyWith(sort: 'last_seen', descending: true));
    }
  }

  Widget _buildFilters(
    BuildContext context, {
    required List<SegmentInfo> segments,
    required String? selectedSegment,
    required CustomerQuery query,
  }) {
    if (Responsive.isMobile(context)) {
      return Column(
        children: [
          TextField(
            controller: _searchController,
            onChanged: _onSearchChanged,
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search, size: 20),
              hintText: 'Search customer ID...',
              isDense: true,
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: InputDecorator(
                  decoration: const InputDecoration(
                    labelText: 'Segment',
                    isDense: true,
                    contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  ),
                  child: DropdownButtonHideUnderline(
                    child: DropdownButton<String?>(
                      isExpanded: true,
                      isDense: true,
                      value: selectedSegment,
                      items: [
                        const DropdownMenuItem<String?>(value: null, child: Text('All segments', overflow: TextOverflow.ellipsis)),
                        for (final segment in segments)
                          DropdownMenuItem<String?>(
                            value: segment.key,
                            child: Text('${segment.name} (${formatCount(segment.customers)})', overflow: TextOverflow.ellipsis),
                          ),
                      ],
                      onChanged: (value) => _update(
                        (q) => value == null ? q.copyWith(clearSegment: true) : q.copyWith(segment: value),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
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
                        DropdownMenuItem(value: 'last_seen', child: Text('Recent', overflow: TextOverflow.ellipsis)),
                        DropdownMenuItem(value: 'spend', child: Text('Spend', overflow: TextOverflow.ellipsis)),
                        DropdownMenuItem(value: 'orders', child: Text('Orders', overflow: TextOverflow.ellipsis)),
                        DropdownMenuItem(value: 'rfm', child: Text('RFM', overflow: TextOverflow.ellipsis)),
                        DropdownMenuItem(value: 'recency', child: Text('Recency', overflow: TextOverflow.ellipsis)),
                      ],
                      onChanged: _onSortChanged,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      );
    }

    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 260,
          child: TextField(
            controller: _searchController,
            onChanged: _onSearchChanged,
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              hintText: 'Search customer ID',
              isDense: true,
            ),
          ),
        ),
        SizedBox(
          width: 240,
          child: InputDecorator(
            decoration: const InputDecoration(
              labelText: 'Segment',
              isDense: true,
              contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            ),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<String?>(
                isExpanded: true,
                isDense: true,
                value: selectedSegment,
                items: [
                  const DropdownMenuItem<String?>(value: null, child: Text('All segments')),
                  for (final segment in segments)
                    DropdownMenuItem<String?>(
                      value: segment.key,
                      child: Text('${segment.name} (${formatCount(segment.customers)})', overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: (value) => _update(
                  (q) => value == null ? q.copyWith(clearSegment: true) : q.copyWith(segment: value),
                ),
              ),
            ),
          ),
        ),
        SizedBox(
          width: 210,
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
                  DropdownMenuItem(value: 'last_seen', child: Text('Recently active')),
                  DropdownMenuItem(value: 'spend', child: Text('Highest spend')),
                  DropdownMenuItem(value: 'orders', child: Text('Most orders')),
                  DropdownMenuItem(value: 'rfm', child: Text('Best RFM score')),
                  DropdownMenuItem(value: 'recency', child: Text('Longest since last order')),
                ],
                onChanged: _onSortChanged,
              ),
            ),
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final query = ref.watch(customerQueryProvider);
    final pageAsync = ref.watch(customersPageProvider);
    final overviewAsync = ref.watch(customerOverviewProvider);
    final segments = ref.watch(segmentOverviewProvider).valueOrNull?.segments ?? const [];
    final selectedSegment = segments.any((s) => s.key == query.segment) ? query.segment : null;

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(customersPageProvider);
        ref.invalidate(customerOverviewProvider);
        ref.invalidate(segmentOverviewProvider);
      },
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: Padding(
          padding: const EdgeInsets.only(bottom: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Customers', style: textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
                        const SizedBox(height: 4),
                        Text('Everyone seen in your events, with RFM score and segment.', style: textTheme.bodyMedium),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  const RecomputeButton(),
                ],
              ),
              const SizedBox(height: 16),
              overviewAsync.maybeWhen(
                data: (overview) => _KpiStrip(overview: overview),
                orElse: () => const SizedBox.shrink(),
              ),
              _buildFilters(
                context,
                segments: segments,
                selectedSegment: selectedSegment,
                query: query,
              ),
              const SizedBox(height: 16),
              pageAsync.when(
                loading: () => const Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: LoadingState(message: 'Loading customers...'),
                ),
                error: (error, _) => ErrorState(
                  message: errorMessageOf(error),
                  onRetry: () => ref.invalidate(customersPageProvider),
                ),
                data: (page) {
                  if (page.items.isEmpty) {
                    return const Padding(
                      padding: EdgeInsets.symmetric(vertical: 40),
                      child: EmptyState(
                        title: 'No customers found',
                        subtitle: 'Try a different search or segment, or press Recompute after sending events.',
                        icon: Icons.people_outline,
                      ),
                    );
                  }
                  return Column(
                    children: [
                      Card(
                        clipBehavior: Clip.antiAlias,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                        elevation: 0,
                        child: Column(
                          children: [
                            for (int i = 0; i < page.items.length; i++) ...[
                              if (i > 0) const Divider(height: 1),
                              _CustomerRow(customer: page.items[i]),
                            ],
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),
                      _Pager(page: page, onPage: (target) => _update((q) => q.copyWith(page: target))),
                    ],
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _KpiStrip extends StatelessWidget {
  const _KpiStrip({required this.overview});

  final CustomerOverview overview;

  @override
  Widget build(BuildContext context) {
    final tiles = <(String, String)>[
      ('Customers', formatCount(overview.customers)),
      ('Buyers', formatCount(overview.buyers)),
      ('Repeat rate', formatPercent(overview.repeatRate)),
      ('Avg order value', formatCompactPrice(overview.avgOrderValue)),
      ('Revenue', formatCompactPrice(overview.revenue)),
      ('Active (${overview.activeDays}d)', formatCount(overview.activeCustomers)),
    ];
    final textTheme = Theme.of(context).textTheme;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    if (Responsive.isMobile(context)) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          physics: const BouncingScrollPhysics(),
          child: Row(
            children: [
              for (int i = 0; i < tiles.length; i++) ...[
                if (i > 0) const SizedBox(width: 10),
                Container(
                  width: 135,
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: isDark ? AppColors.cardDarkElevated : Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: isDark ? AppColors.borderDark : AppColors.borderLight,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.03),
                        blurRadius: 6,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        tiles[i].$2,
                        style: textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.2,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 3),
                      Text(
                        tiles[i].$1,
                        style: textTheme.bodySmall?.copyWith(
                          color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
                          fontSize: 11.5,
                          fontWeight: FontWeight.w500,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final w = constraints.maxWidth;
          final cols = w < 720 ? 3 : 6;
          final tileWidth = (w - (cols - 1) * 12) / cols;

          return Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final tile in tiles)
                Container(
                  width: tileWidth,
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: isDark ? AppColors.cardDarkElevated : Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: isDark ? AppColors.borderDark : AppColors.borderLight,
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(tile.$2, style: textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700), maxLines: 1, overflow: TextOverflow.ellipsis),
                      const SizedBox(height: 2),
                      Text(tile.$1, style: textTheme.bodyMedium?.copyWith(fontSize: 12), overflow: TextOverflow.ellipsis),
                    ],
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}

class _CustomerRow extends StatelessWidget {
  const _CustomerRow({required this.customer});

  final Customer customer;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final stats = customer.stats;
    final detail = <String>[
      '${stats.orders} ${stats.orders == 1 ? 'order' : 'orders'}',
      if (customer.favoriteCategory != null) customer.favoriteCategory!,
      if (customer.rfm.code != null) 'RFM ${customer.rfm.code}',
    ].join(' • ');
    final segment = customer.segment;

    return InkWell(
      onTap: () => context.go('/customers/${Uri.encodeComponent(customer.id)}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            CircleAvatar(
              radius: 20,
              backgroundColor: segmentColor(segment?.key).withValues(alpha: 0.14),
              child: Icon(Icons.person_outline, size: 20, color: segmentColor(segment?.key)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    customer.id,
                    style: textTheme.titleMedium?.copyWith(fontSize: 14),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    detail,
                    style: textTheme.bodyMedium?.copyWith(fontSize: 12),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(formatCompactPrice(stats.totalSpend), style: textTheme.titleMedium?.copyWith(fontSize: 14)),
                const SizedBox(height: 4),
                SegmentChip(segmentKey: segment?.key, label: segment?.name ?? 'Not scored'),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Pager extends StatelessWidget {
  const _Pager({required this.page, required this.onPage});

  final CustomerPage page;
  final void Function(int page) onPage;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: isDark ? AppColors.cardDarkElevated : Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isDark ? AppColors.borderDark : AppColors.borderLight,
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              '${formatCount(page.total)} customers  •  Page ${page.page} of ${page.totalPages}',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          IconButton.filledTonal(
            tooltip: 'Previous page',
            icon: const Icon(Icons.chevron_left, size: 20),
            onPressed: page.page > 1 ? () => onPage(page.page - 1) : null,
          ),
          const SizedBox(width: 8),
          IconButton.filledTonal(
            tooltip: 'Next page',
            icon: const Icon(Icons.chevron_right, size: 20),
            onPressed: page.page < page.totalPages ? () => onPage(page.page + 1) : null,
          ),
        ],
      ),
    );
  }
}
