import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/adaptive_grid.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../domain/report.dart';
import '../providers/analytics_providers.dart';
import '../widgets/value_bars.dart';

enum _Metric { revenue, orders, events, activeCustomers, newCustomers }

extension on _Metric {
  String get label {
    switch (this) {
      case _Metric.revenue:
        return 'Revenue';
      case _Metric.orders:
        return 'Orders';
      case _Metric.events:
        return 'Events';
      case _Metric.activeCustomers:
        return 'Active customers';
      case _Metric.newCustomers:
        return 'New customers';
    }
  }

  double valueOf(DailyPoint p) {
    switch (this) {
      case _Metric.revenue:
        return p.revenue;
      case _Metric.orders:
        return p.orders.toDouble();
      case _Metric.events:
        return p.events.toDouble();
      case _Metric.activeCustomers:
        return p.activeCustomers.toDouble();
      case _Metric.newCustomers:
        return p.newCustomers.toDouble();
    }
  }

  String format(double v) => this == _Metric.revenue ? formatPrice(v) : formatCount(v.round());
}

class AnalyticsScreen extends ConsumerStatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  ConsumerState<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends ConsumerState<AnalyticsScreen> {
  _Metric _metric = _Metric.revenue;
  bool _isRefreshing = false;

  Future<void> _handleRefresh() async {
    if (_isRefreshing) return;
    setState(() => _isRefreshing = true);

    try {
      await ref.refresh(analyticsReportProvider.future);
      if (mounted) {
        ScaffoldMessenger.of(context).clearSnackBars();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Row(
              children: [
                Icon(Icons.check_circle_rounded, color: Colors.white, size: 18),
                SizedBox(width: 8),
                Text('Analytics data refreshed successfully!'),
              ],
            ),
            backgroundColor: AppColors.success,
            duration: Duration(seconds: 2),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).clearSnackBars();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to refresh analytics: $e'),
            backgroundColor: AppColors.danger,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isRefreshing = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final days = ref.watch(analyticsDaysProvider);
    final reportAsync = ref.watch(analyticsReportProvider);

    return RefreshIndicator(
      onRefresh: _handleRefresh,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
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
                      Text('Analytics', style: textTheme.headlineSmall),
                      const SizedBox(height: 4),
                      Text('How your store is doing, compared with the period before.', style: textTheme.bodyMedium),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Refresh',
                  icon: _isRefreshing
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.refresh_rounded),
                  onPressed: _isRefreshing ? null : _handleRefresh,
                ),
              ],
            ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final option in const [7, 14, 30, 90])
                ChoiceChip(
                  label: Text('Last $option days'),
                  selected: days == option,
                  onSelected: (_) => ref.read(analyticsDaysProvider.notifier).state = option,
                ),
            ],
          ),
          const SizedBox(height: 16),
          reportAsync.when(
            loading: () => const Padding(padding: EdgeInsets.all(32), child: LoadingState(message: 'Crunching numbers...')),
            error: (error, _) => ErrorState(
              message: errorMessageOf(error),
              onRetry: () => ref.invalidate(analyticsReportProvider),
            ),
            data: (report) => _ReportBody(
              report: report,
              metric: _metric,
              onMetric: (metric) => setState(() => _metric = metric),
            ),
          ),
        ],
      ),
    ),
  );
}
}

class _ReportBody extends StatelessWidget {
  const _ReportBody({required this.report, required this.metric, required this.onMetric});

  final AnalyticsReport report;
  final _Metric metric;
  final ValueChanged<_Metric> onMetric;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    final kpiTiles = <(String, Kpi, String Function(double))>[
      ('Revenue', report.kpi('revenue'), formatCompactPrice),
      ('Orders', report.kpi('orders'), (v) => formatCount(v.round())),
      ('Avg order value', report.kpi('avg_order_value'), formatCompactPrice),
      ('Active customers', report.kpi('active_customers'), (v) => formatCount(v.round())),
      ('New customers', report.kpi('new_customers'), (v) => formatCount(v.round())),
      ('Conversion', report.kpi('conversion_rate'), formatPercent),
      ('Events', report.kpi('events'), (v) => formatCount(v.round())),
    ];

    final daily = report.daily;
    final sumRecs = daily.fold<int>(0, (sum, d) => sum + d.recsServed);
    final recViews = daily.fold<int>(0, (sum, d) => sum + d.recViews);
    final recClicks = daily.fold<int>(0, (sum, d) => sum + d.recClicks);
    final offerImpressions = daily.fold<int>(0, (sum, d) => sum + d.offerImpressions);
    final offerClicks = daily.fold<int>(0, (sum, d) => sum + d.offerClicks);
    final redemptions = daily.fold<int>(0, (sum, d) => sum + d.offerRedemptions);
    final discount = daily.fold<double>(0, (sum, d) => sum + d.offerDiscount);

    final chart = _Section(
      title: '${metric.label} per day',
      subtitle: '${report.from} to ${report.to}',
      trailing: Wrap(
        spacing: 6,
        runSpacing: 6,
        children: [
          for (final option in _Metric.values)
            ChoiceChip(
              label: Text(option.label),
              selected: option == metric,
              visualDensity: VisualDensity.compact,
              onSelected: (_) => onMetric(option),
            ),
        ],
      ),
      child: ValueBars(
        values: [for (final d in daily) metric.valueOf(d)],
        dates: [for (final d in daily) d.date],
        format: metric.format,
      ),
    );

    final funnel = _Section(
      title: 'Customer funnel',
      subtitle: 'Distinct customers reaching each step',
      child: Column(
        children: [
          for (final step in report.funnel)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(child: Text(step.label, style: textTheme.bodyLarge)),
                      Text(formatCount(step.customers), style: textTheme.titleMedium?.copyWith(fontSize: 14)),
                    ],
                  ),
                  const SizedBox(height: 4),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: (step.rateFromStart ?? 0).clamp(0.0, 1.0).toDouble(),
                      minHeight: 8,
                      backgroundColor: AppColors.primary.withValues(alpha: 0.12),
                      valueColor: const AlwaysStoppedAnimation<Color>(AppColors.primary),
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${formatPercent(step.rateFromStart)} of viewers  •  ${formatPercent(step.rateFromPrevious)} of previous step',
                    style: textTheme.bodyMedium?.copyWith(fontSize: 12),
                  ),
                ],
              ),
            ),
        ],
      ),
    );

    final platforms = _Section(
      title: 'Platforms',
      subtitle: 'Where the events come from',
      child: report.platforms.isEmpty
          ? Text('No events in this period.', style: textTheme.bodyMedium)
          : Column(
              children: [
                for (final p in report.platforms)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(child: Text(humanize(p.platform), style: textTheme.bodyMedium)),
                            Text('${formatPercent(p.share)}  •  ${formatCount(p.events)}', style: textTheme.bodyMedium),
                          ],
                        ),
                        const SizedBox(height: 4),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(4),
                          child: LinearProgressIndicator(
                            value: p.share.clamp(0.0, 1.0).toDouble(),
                            minHeight: 6,
                            backgroundColor: AppColors.info.withValues(alpha: 0.12),
                            valueColor: const AlwaysStoppedAnimation<Color>(AppColors.info),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
    );

    final products = _Section(
      title: 'Top products by revenue',
      child: report.topProducts.isEmpty
          ? Text('No purchases in this period.', style: textTheme.bodyMedium)
          : Column(
              children: [
                for (var i = 0; i < report.topProducts.length; i++) ...[
                  if (i > 0) const Divider(height: 1),
                  _ProductRow(rank: i + 1, product: report.topProducts[i]),
                ],
              ],
            ),
    );

    final categories = _Section(
      title: 'Top categories by revenue',
      child: report.topCategories.isEmpty
          ? Text('No purchases in this period.', style: textTheme.bodyMedium)
          : Column(
              children: [
                for (final c in report.topCategories)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(child: Text(c.category, style: textTheme.bodyMedium, overflow: TextOverflow.ellipsis)),
                            Text('${formatCompactPrice(c.revenue)}  •  ${formatPercent(c.share)}', style: textTheme.bodyMedium),
                          ],
                        ),
                        const SizedBox(height: 4),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(4),
                          child: LinearProgressIndicator(
                            value: c.share.clamp(0.0, 1.0).toDouble(),
                            minHeight: 6,
                            backgroundColor: AppColors.success.withValues(alpha: 0.12),
                            valueColor: const AlwaysStoppedAnimation<Color>(AppColors.success),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
    );

    final marketing = _Section(
      title: 'Recommendations and offers',
      subtitle: 'In this period',
      child: AdaptiveGrid(
        itemMinWidth: 140,
        children: [
          _MiniStat('Recommendation requests', formatCount(sumRecs)),
          _MiniStat('Recommendation CTR', formatPercent(recViews == 0 ? null : recClicks / recViews)),
          _MiniStat('Offer impressions', formatCount(offerImpressions)),
          _MiniStat('Offer clicks', formatCount(offerClicks)),
          _MiniStat('Offers redeemed', formatCount(redemptions)),
          _MiniStat('Discount given', formatCompactPrice(discount)),
        ],
      ),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        AdaptiveGrid(
          itemMinWidth: 150,
          children: [
            for (final tile in kpiTiles) _KpiTile(label: tile.$1, kpi: tile.$2, format: tile.$3, days: report.days),
          ],
        ),
        const SizedBox(height: 16),
        chart,
        const SizedBox(height: 16),
        LayoutBuilder(
          builder: (context, constraints) {
            if (constraints.maxWidth >= 900) {
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: funnel),
                  const SizedBox(width: 16),
                  Expanded(child: platforms),
                ],
              );
            }
            return Column(children: [funnel, const SizedBox(height: 16), platforms]);
          },
        ),
        const SizedBox(height: 16),
        LayoutBuilder(
          builder: (context, constraints) {
            if (constraints.maxWidth >= 900) {
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(flex: 3, child: products),
                  const SizedBox(width: 16),
                  Expanded(flex: 2, child: categories),
                ],
              );
            }
            return Column(children: [products, const SizedBox(height: 16), categories]);
          },
        ),
        const SizedBox(height: 16),
        marketing,
      ],
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.child, this.subtitle, this.trailing});

  final String title;
  final String? subtitle;
  final Widget? trailing;
  final Widget child;

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
              Text(title, style: textTheme.titleMedium),
              if (subtitle != null) ...[
                const SizedBox(height: 2),
                Text(subtitle!, style: textTheme.bodyMedium),
              ],
              if (trailing != null) ...[
                const SizedBox(height: 10),
                trailing!,
              ],
              const SizedBox(height: 16),
              child,
            ],
          ),
        ),
      ),
    );
  }
}

class _KpiTile extends StatelessWidget {
  const _KpiTile({required this.label, required this.kpi, required this.format, required this.days});

  final String label;
  final Kpi kpi;
  final String Function(double value) format;
  final int days;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final change = kpi.change;
    final color = change == null
        ? const Color(0xFF9CA3AF)
        : (change > 0 ? AppColors.success : (change < 0 ? AppColors.danger : const Color(0xFF9CA3AF)));
    final icon = change == null || change == 0
        ? Icons.remove
        : (change > 0 ? Icons.arrow_upward : Icons.arrow_downward);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.primary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: textTheme.bodyMedium?.copyWith(fontSize: 12)),
          const SizedBox(height: 4),
          Text(format(kpi.value), style: textTheme.titleLarge, maxLines: 1, overflow: TextOverflow.ellipsis),
          const SizedBox(height: 6),
          Row(
            children: [
              Icon(icon, size: 14, color: color),
              const SizedBox(width: 3),
              Expanded(
                child: Text(
                  change == null ? 'no previous data' : '${formatChange(change)} vs previous $days days',
                  style: TextStyle(color: color, fontSize: 11.5, fontWeight: FontWeight.w600),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _MiniStat extends StatelessWidget {
  const _MiniStat(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.primary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: textTheme.titleMedium),
          const SizedBox(height: 2),
          Text(label, style: textTheme.bodyMedium?.copyWith(fontSize: 12), maxLines: 2, overflow: TextOverflow.ellipsis),
        ],
      ),
    );
  }
}

class _ProductRow extends StatelessWidget {
  const _ProductRow({required this.rank, required this.product});

  final int rank;
  final TopProduct product;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final small = textTheme.bodyMedium?.copyWith(fontSize: 12);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        children: [
          SizedBox(width: 26, child: Text('$rank', style: textTheme.titleMedium)),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(product.name, style: textTheme.titleMedium?.copyWith(fontSize: 14), maxLines: 1, overflow: TextOverflow.ellipsis),
                Text(
                  [product.productId, if (product.category != null) product.category!].join(' • '),
                  style: small,
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
              Text(formatCompactPrice(product.revenue), style: textTheme.titleMedium?.copyWith(fontSize: 14)),
              Text('${formatCount(product.units)} sold • ${formatCount(product.views)} views', style: small),
            ],
          ),
        ],
      ),
    );
  }
}
