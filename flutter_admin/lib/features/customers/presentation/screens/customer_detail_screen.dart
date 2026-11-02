import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../../offers/presentation/providers/offers_providers.dart';
import '../../../offers/presentation/widgets/offer_suggestion_tile.dart';
import '../../../recommendations/presentation/providers/recommendations_providers.dart';
import '../../../recommendations/presentation/widgets/recommendation_tile.dart';
import '../../../segments/presentation/widgets/segment_chip.dart';
import '../../domain/customer.dart';
import '../providers/customers_providers.dart';
import '../../../models/presentation/providers/ml_providers.dart';

class CustomerDetailScreen extends ConsumerWidget {
  const CustomerDetailScreen({super.key, required this.customerId});

  final String customerId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final customerAsync = ref.watch(customerDetailProvider(customerId));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: () => context.go('/customers'),
            icon: const Icon(Icons.arrow_back, size: 18),
            label: const Text('All customers'),
          ),
        ),
        Expanded(
          child: customerAsync.when(
            loading: () => const LoadingState(message: 'Loading customer...'),
            error: (error, _) => ErrorState(
              message: errorMessageOf(error),
              onRetry: () => ref.invalidate(customerDetailProvider(customerId)),
            ),
            data: (customer) => _Detail(customer: customer),
          ),
        ),
      ],
    );
  }
}

class _Detail extends ConsumerWidget {
  const _Detail({required this.customer});

  final Customer customer;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final segment = customer.segment;

    final header = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 12,
          runSpacing: 6,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(customer.id, style: textTheme.headlineSmall),
            SegmentChip(segmentKey: segment?.key, label: segment?.name ?? 'Not scored yet'),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          'First seen ${customer.firstSeenAt == null ? '—' : formatTimestamp(customer.firstSeenAt!)}'
          '  •  last seen ${customer.lastSeenAt == null ? '—' : formatTimestamp(customer.lastSeenAt!)}',
          style: textTheme.bodyMedium,
        ),
        const SizedBox(height: 14),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: segment == null
                ? Text(
                    'This customer has not been scored yet. Open Segments and press Recompute.',
                    style: textTheme.bodyMedium,
                  )
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(segment.description ?? '', style: textTheme.bodyMedium),
                      if (segment.action != null) ...[
                        const SizedBox(height: 8),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(Icons.lightbulb_outline, size: 16, color: segmentColor(segment.key)),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                segment.action!,
                                style: textTheme.bodyMedium?.copyWith(fontStyle: FontStyle.italic),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
          ),
        ),
        const SizedBox(height: 16),
      ],
    );

    final left = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _Metrics(customer: customer),
        const SizedBox(height: 16),
        _RfmCard(customer: customer),
        const SizedBox(height: 16),
        _InterestsCard(customer: customer),
      ],
    );

    final right = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Recommended for this customer', style: textTheme.titleMedium),
                const SizedBox(height: 4),
                RecommendationList(
                  result: ref.watch(userRecommendationsProvider(customer.id)),
                  emptyText: 'No recommendations yet.',
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        _OffersCard(customerId: customer.id),
        const SizedBox(height: 16),
        _MlPredictionsCard(customerId: customer.id),
        const SizedBox(height: 16),
        _TimelineCard(customerId: customer.id),
      ],
    );

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          header,
          LayoutBuilder(
            builder: (context, constraints) {
              if (constraints.maxWidth >= 900) {
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: left),
                    const SizedBox(width: 16),
                    Expanded(child: right),
                  ],
                );
              }
              return Column(children: [left, const SizedBox(height: 16), right]);
            },
          ),
        ],
      ),
    );
  }
}

class _Metrics extends StatelessWidget {
  const _Metrics({required this.customer});

  final Customer customer;

  @override
  Widget build(BuildContext context) {
    final s = customer.stats;
    final tiles = <(String, String)>[
      ('Total spend', formatPrice(s.totalSpend)),
      ('Orders', formatCount(s.orders)),
      ('Avg order value', formatPrice(s.avgOrderValue)),
      ('Last order', s.orders == 0 ? '—' : formatDaysAgo(s.recencyDays)),
      ('Items purchased', formatCount(s.itemsPurchased)),
      ('Returns', formatCount(s.returns)),
      ('Events', formatCount(s.events)),
      ('Active days', formatCount(s.activeDays)),
      ('Product views', formatCount(s.views)),
      ('Cart adds', formatCount(s.cartAdds)),
    ];
    final textTheme = Theme.of(context).textTheme;

    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        for (final tile in tiles)
          Container(
            width: 150,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.primary.withValues(alpha: 0.06),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(tile.$2, style: textTheme.titleMedium, maxLines: 1, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 2),
                Text(tile.$1, style: textTheme.bodyMedium?.copyWith(fontSize: 12)),
              ],
            ),
          ),
      ],
    );
  }
}

class _RfmCard extends StatelessWidget {
  const _RfmCard({required this.customer});

  final Customer customer;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final rfm = customer.rfm;
    final stats = customer.stats;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('RFM score${rfm.code == null ? '' : '  ·  ${rfm.code}'}', style: textTheme.titleMedium),
            const SizedBox(height: 12),
            if (!rfm.isScored)
              Text(
                'RFM needs at least one purchase. This customer has not bought anything yet.',
                style: textTheme.bodyMedium,
              )
            else ...[
              _ScoreRow(label: 'Recency', score: rfm.r!, caption: formatDaysAgo(stats.recencyDays)),
              _ScoreRow(label: 'Frequency', score: rfm.f!, caption: '${stats.orders} orders'),
              _ScoreRow(label: 'Monetary', score: rfm.m!, caption: formatCompactPrice(stats.totalSpend)),
            ],
          ],
        ),
      ),
    );
  }
}

class _ScoreRow extends StatelessWidget {
  const _ScoreRow({required this.label, required this.score, required this.caption});

  final String label;
  final int score;
  final String caption;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          SizedBox(width: 84, child: Text(label, style: textTheme.bodyMedium)),
          for (var i = 1; i <= 5; i++)
            Container(
              width: 26,
              height: 10,
              margin: const EdgeInsets.only(right: 4),
              decoration: BoxDecoration(
                color: i <= score ? AppColors.primary : AppColors.primary.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(3),
              ),
            ),
          const SizedBox(width: 8),
          Text('$score/5', style: textTheme.titleMedium?.copyWith(fontSize: 13)),
          const SizedBox(width: 10),
          Expanded(child: Text(caption, style: textTheme.bodyMedium?.copyWith(fontSize: 12), overflow: TextOverflow.ellipsis)),
        ],
      ),
    );
  }
}

class _InterestsCard extends StatelessWidget {
  const _InterestsCard({required this.customer});

  final Customer customer;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Card(
      child: SizedBox(
        width: double.infinity,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Interests', style: textTheme.titleMedium),
              const SizedBox(height: 10),
              if (customer.favoriteCategory == null && customer.favoriteBrand == null)
                Text('No interests detected yet.', style: textTheme.bodyMedium)
              else
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if (customer.favoriteCategory != null)
                      Chip(
                        visualDensity: VisualDensity.compact,
                        avatar: const Icon(Icons.category_outlined, size: 16),
                        label: Text(customer.favoriteCategory!),
                      ),
                    if (customer.favoriteBrand != null)
                      Chip(
                        visualDensity: VisualDensity.compact,
                        avatar: const Icon(Icons.business_outlined, size: 16),
                        label: Text(customer.favoriteBrand!),
                      ),
                  ],
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _OffersCard extends ConsumerWidget {
  const _OffersCard({required this.customerId});

  final String customerId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final offersAsync = ref.watch(customerOffersProvider(customerId));

    return Card(
      child: SizedBox(
        width: double.infinity,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Offers for this customer', style: textTheme.titleMedium),
              const SizedBox(height: 4),
              offersAsync.when(
                loading: () => const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: Center(child: SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5))),
                ),
                error: (error, _) => Text(errorMessageOf(error), style: textTheme.bodyMedium),
                data: (offers) {
                  if (offers.isEmpty) {
                    return Text('No offers apply to this customer right now.', style: textTheme.bodyMedium);
                  }
                  return Column(
                    children: [
                      for (var i = 0; i < offers.length; i++) ...[
                        if (i > 0) const Divider(height: 1),
                        OfferSuggestionTile(offer: offers[i]),
                      ],
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

IconData _iconForEvent(String type) {
  switch (type) {
    case 'PRODUCT_VIEW':
      return Icons.visibility_outlined;
    case 'ADD_TO_CART':
      return Icons.add_shopping_cart;
    case 'PURCHASE':
      return Icons.shopping_bag_outlined;
    case 'WISHLIST_ADD':
      return Icons.favorite_border;
    case 'RETURN':
    case 'PURCHASE_CANCELLED':
    case 'REMOVE_FROM_CART':
      return Icons.undo;
    case 'PRODUCT_SEARCH':
      return Icons.search;
    case 'CATEGORY_VIEW':
      return Icons.category_outlined;
    case 'RECOMMENDATION_VIEW':
    case 'RECOMMENDATION_CLICK':
      return Icons.auto_awesome_outlined;
    case 'OFFER_VIEW':
    case 'OFFER_CLICK':
    case 'OFFER_REDEEM':
      return Icons.local_offer_outlined;
    default:
      return Icons.bolt_outlined;
  }
}

class _TimelineCard extends ConsumerStatefulWidget {
  const _TimelineCard({required this.customerId});

  final String customerId;

  @override
  ConsumerState<_TimelineCard> createState() => _TimelineCardState();
}

class _TimelineCardState extends ConsumerState<_TimelineCard> {
  int _page = 1;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final timelineAsync = ref.watch(customerTimelineProvider((widget.customerId, _page)));

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Behaviour timeline', style: textTheme.titleMedium),
            const SizedBox(height: 8),
            timelineAsync.when(
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5))),
              ),
              error: (error, _) => Text(errorMessageOf(error), style: textTheme.bodyMedium),
              data: (page) {
                if (page.items.isEmpty) {
                  return Text('No events recorded.', style: textTheme.bodyMedium);
                }
                return Column(
                  children: [
                    for (var i = 0; i < page.items.length; i++) ...[
                      if (i > 0) const Divider(height: 1),
                      _TimelineRow(event: page.items[i]),
                    ],
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${formatCount(page.total)} events  •  page ${page.page} of ${page.totalPages}',
                            style: textTheme.bodyMedium?.copyWith(fontSize: 12),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        IconButton(
                          tooltip: 'Newer',
                          icon: const Icon(Icons.chevron_left),
                          onPressed: page.page > 1 ? () => setState(() => _page = page.page - 1) : null,
                        ),
                        IconButton(
                          tooltip: 'Older',
                          icon: const Icon(Icons.chevron_right),
                          onPressed: page.page < page.totalPages ? () => setState(() => _page = page.page + 1) : null,
                        ),
                      ],
                    ),
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({required this.event});

  final TimelineEvent event;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final subject = event.productName ?? event.productId;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Icon(_iconForEvent(event.eventType), size: 18, color: AppColors.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  subject == null ? humanize(event.eventType) : '${humanize(event.eventType)} · $subject',
                  style: textTheme.bodyLarge,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  [
                    formatTimestamp(event.occurredAt),
                    if (event.category != null) event.category!,
                    if (event.platform != null) event.platform!,
                  ].join(' • '),
                  style: textTheme.bodyMedium?.copyWith(fontSize: 12),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ML Predictions Card (Phase 7)
// ─────────────────────────────────────────────────────────────────────────────

class _MlPredictionsCard extends ConsumerWidget {
  const _MlPredictionsCard({required this.customerId});

  final String customerId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(mlCustomerProfileProvider(customerId));
    final textTheme = Theme.of(context).textTheme;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.psychology_rounded, size: 18, color: Color(0xFF7C3AED)),
                const SizedBox(width: 8),
                Text('ML Predictions', style: textTheme.titleMedium),
              ],
            ),
            const SizedBox(height: 12),
            async.when(
              loading: () => const SizedBox(
                height: 48,
                child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
              ),
              error: (_, __) => Text(
                'ML predictions not available — run Rebuild Models in the ML Insights screen.',
                style: textTheme.bodyMedium,
              ),
              data: (profile) {
                if (profile == null) {
                  return Text(
                    'No ML scores yet — open ML Insights and tap Rebuild Models.',
                    style: textTheme.bodyMedium,
                  );
                }
                return Column(
                  children: [
                    if (profile.purchaseProbability != null)
                      _MlScoreRow(
                        label: 'Purchase (30d)',
                        score: profile.purchaseProbability!.score,
                        label2: profile.purchaseProbability!.label,
                        color: AppColors.success,
                      ),
                    if (profile.churnRisk != null)
                      _MlScoreRow(
                        label: 'Churn Risk',
                        score: profile.churnRisk!.score,
                        label2: profile.churnRisk!.label,
                        color: profile.churnRisk!.label == 'high'
                            ? AppColors.danger
                            : profile.churnRisk!.label == 'medium'
                                ? AppColors.warning
                                : AppColors.success,
                      ),
                    if (profile.offerResponse != null) ...[
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: AppColors.info.withValues(alpha: 0.08),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: AppColors.info.withValues(alpha: 0.2)),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.local_offer_outlined, size: 16, color: AppColors.info),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                'Best offer type: ${profile.offerResponse!.recommendedOfferType.replaceAll('_', ' ').toUpperCase()}',
                                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _MlScoreRow extends StatelessWidget {
  const _MlScoreRow({
    required this.label,
    required this.score,
    required this.label2,
    required this.color,
  });

  final String label;
  final double score;
  final String label2;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          SizedBox(
            width: 110,
            child: Text(label, style: const TextStyle(fontSize: 12)),
          ),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: score.clamp(0.0, 1.0),
                backgroundColor: isDark ? AppColors.borderDark : AppColors.borderLight,
                valueColor: AlwaysStoppedAnimation<Color>(color),
                minHeight: 6,
              ),
            ),
          ),
          const SizedBox(width: 8),
          Text(
            '${(score * 100).toStringAsFixed(0)}%',
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color),
          ),
          const SizedBox(width: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              label2.toUpperCase(),
              style: TextStyle(fontSize: 9, fontWeight: FontWeight.w700, color: color),
            ),
          ),
        ],
      ),
    );
  }
}
