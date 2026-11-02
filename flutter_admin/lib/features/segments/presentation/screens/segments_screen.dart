import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../../customers/domain/customer.dart';
import '../../../customers/presentation/providers/customers_providers.dart';
import '../../domain/segment.dart';
import '../providers/segments_providers.dart';
import '../widgets/recompute_button.dart';
import '../widgets/segment_chip.dart';

class SegmentsScreen extends ConsumerWidget {
  const SegmentsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final overviewAsync = ref.watch(segmentOverviewProvider);

    return SingleChildScrollView(
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
                    Text('Customer Segments', style: textTheme.headlineSmall),
                    const SizedBox(height: 4),
                    Text(
                      'Customers are scored 1-5 on Recency, Frequency and Monetary value (RFM) '
                      'and grouped into segments you can target.',
                      style: textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              const RecomputeButton(),
            ],
          ),
          const SizedBox(height: 20),
          overviewAsync.when(
            loading: () => const Padding(padding: EdgeInsets.all(32), child: LoadingState(message: 'Loading segments...')),
            error: (error, _) => ErrorState(
              message: 'Could not load segments. Is the backend running?',
              onRetry: () => ref.invalidate(segmentOverviewProvider),
            ),
            data: (overview) => _Content(overview: overview),
          ),
        ],
      ),
    );
  }
}

class _Content extends ConsumerWidget {
  const _Content({required this.overview});

  final SegmentOverview overview;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;

    if (overview.totalCustomers == 0) {
      return const EmptyState(
        title: 'No customer profiles yet',
        subtitle: 'Send customer events to the API (or run the seed script), then press Recompute.',
        icon: Icons.donut_small_outlined,
      );
    }

    void viewSegment(String key) {
      ref.read(customerQueryProvider.notifier).state = const CustomerQuery().copyWith(segment: key);
      context.go('/customers');
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '${formatCount(overview.totalCustomers)} customers'
          '${overview.profilesComputedAt == null ? '' : '  •  computed ${formatTimestamp(overview.profilesComputedAt!)}'}',
          style: textTheme.bodyMedium,
        ),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('RFM grid', style: textTheme.titleMedium),
                const SizedBox(height: 2),
                Text(
                  'Buyers by Recency (rows, 5 = bought most recently) and Frequency (columns, 5 = orders most often).',
                  style: textTheme.bodyMedium,
                ),
                const SizedBox(height: 14),
                _RfmGrid(cells: overview.grid),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        LayoutBuilder(
          builder: (context, constraints) {
            final columns = constraints.maxWidth >= 980 ? 3 : (constraints.maxWidth >= 620 ? 2 : 1);
            final width = (constraints.maxWidth - 16 * (columns - 1)) / columns;
            return Wrap(
              spacing: 16,
              runSpacing: 16,
              children: [
                for (final segment in overview.segments)
                  SizedBox(
                    width: width,
                    child: _SegmentCard(segment: segment, onView: () => viewSegment(segment.key)),
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _RfmGrid extends StatelessWidget {
  const _RfmGrid({required this.cells});

  final List<RfmCell> cells;

  @override
  Widget build(BuildContext context) {
    final counts = <String, int>{for (final cell in cells) '${cell.r}-${cell.f}': cell.count};
    final maxCount = cells.fold<int>(0, (max, cell) => cell.count > max ? cell.count : max);
    final labelStyle = Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 12);

    Widget cellFor(int r, int f) {
      final count = counts['$r-$f'] ?? 0;
      final ratio = maxCount == 0 ? 0.0 : count / maxCount;
      return Expanded(
        child: Tooltip(
          message: 'Recency $r, Frequency $f: $count customers',
          child: Container(
            height: 40,
            margin: const EdgeInsets.all(2),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.primary.withValues(alpha: count == 0 ? 0.05 : 0.15 + 0.85 * ratio),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              count == 0 ? '' : '$count',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: ratio > 0.55 ? Colors.white : null),
            ),
          ),
        ),
      );
    }

    return Column(
      children: [
        for (var r = 5; r >= 1; r--)
          Row(
            children: [
              SizedBox(width: 28, child: Text('R$r', style: labelStyle)),
              for (var f = 1; f <= 5; f++) cellFor(r, f),
            ],
          ),
        const SizedBox(height: 4),
        Row(
          children: [
            const SizedBox(width: 28),
            for (var f = 1; f <= 5; f++) Expanded(child: Center(child: Text('F$f', style: labelStyle))),
          ],
        ),
      ],
    );
  }
}

class _SegmentCard extends StatelessWidget {
  const _SegmentCard({required this.segment, required this.onView});

  final SegmentInfo segment;
  final VoidCallback onView;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final small = textTheme.bodyMedium?.copyWith(fontSize: 12);
    final color = segmentColor(segment.key);

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Container(
        decoration: BoxDecoration(border: Border(top: BorderSide(color: color, width: 4))),
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(segment.name, style: textTheme.titleMedium)),
                Text(formatCount(segment.customers), style: textTheme.titleMedium?.copyWith(color: color)),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              '${formatPercent(segment.share)} of customers  •  ${formatPercent(segment.revenueShare)} of revenue',
              style: small,
            ),
            const SizedBox(height: 8),
            Text(segment.description, style: textTheme.bodyMedium),
            const SizedBox(height: 8),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.lightbulb_outline, size: 15, color: color),
                const SizedBox(width: 6),
                Expanded(child: Text(segment.action, style: small?.copyWith(fontStyle: FontStyle.italic))),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: Text(
                    segment.avgSpend == null
                        ? 'No buyers'
                        : 'Avg spend ${formatCompactPrice(segment.avgSpend)}  •  '
                            '${segment.avgRecencyDays == null ? '—' : '${segment.avgRecencyDays!.round()}d'} since last order',
                    style: small,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                TextButton(
                  onPressed: segment.customers > 0 ? onView : null,
                  child: const Text('View customers'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
