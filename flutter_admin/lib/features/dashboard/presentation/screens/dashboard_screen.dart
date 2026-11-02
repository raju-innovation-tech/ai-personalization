import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../../segments/presentation/providers/segments_providers.dart';
import '../../../segments/presentation/widgets/segment_chip.dart';
import '../../../auth/presentation/providers/auth_controller.dart';
import '../../../auth/presentation/providers/auth_state.dart';
import '../../domain/overview.dart';
import '../../domain/system_health.dart';
import '../providers/dashboard_providers.dart';
import '../widgets/charts.dart';
import '../widgets/kpi_card.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final healthAsync = ref.watch(systemHealthProvider);
    final overviewAsync = ref.watch(dashboardOverviewProvider);
    final overview = overviewAsync.valueOrNull;
    final segmentsAsync = ref.watch(segmentOverviewProvider);
    final authState = ref.watch(authControllerProvider);
    final userName = authState is AuthAuthenticated ? authState.user.fullName : '';

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Welcome back, $userName', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 4),
          Text(
            'Here is a snapshot of your AI Personalization platform.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 24),

          _SystemStatusBanner(healthAsync: healthAsync),
          const SizedBox(height: 24),

          Row(
            children: [
              Expanded(child: Text('Overview', style: Theme.of(context).textTheme.titleLarge)),
              IconButton(
                tooltip: 'Refresh',
                icon: const Icon(Icons.refresh),
                onPressed: () {
                  ref.invalidate(dashboardOverviewProvider);
                  ref.invalidate(systemHealthProvider);
                },
              ),
            ],
          ),
          const SizedBox(height: 4),
          if (overviewAsync.hasError && overview == null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(errorMessageOf(overviewAsync.error!), style: Theme.of(context).textTheme.bodyMedium),
            ),
          // Fixed card height + max card width: a childAspectRatio made the cards
          // too short on desktop (4 columns) and overflowed their content.
          GridView(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
              maxCrossAxisExtent: 360,
              mainAxisExtent: 188,
              crossAxisSpacing: 16,
              mainAxisSpacing: 16,
            ),
            children: [
              KpiCard(
                label: 'Total Customers',
                value: overview == null ? '—' : formatCount(overview.customers),
                icon: Icons.people_alt_outlined,
                subtitle: 'Unique shoppers seen in events',
              ),
              KpiCard(
                label: 'Total Products',
                value: overview == null ? '—' : formatCount(overview.products),
                icon: Icons.inventory_2_outlined,
                accentColor: AppColors.info,
                subtitle: overview == null ? null : '${formatCount(overview.activeProducts)} active in the catalog',
              ),
              KpiCard(
                label: 'Recommendations Served',
                value: overview == null ? '—' : formatCount(overview.recommendationsServed),
                icon: Icons.auto_awesome_outlined,
                accentColor: AppColors.success,
                subtitle: overview == null
                    ? null
                    : '${formatCount(overview.recommendationsServed7d)} in 7 days  •  CTR ${formatPercent(overview.ctr)}',
              ),
              KpiCard(
                label: 'Offers Served',
                value: overview == null ? '—' : formatCount(overview.offersImpressions),
                icon: Icons.local_offer_outlined,
                accentColor: AppColors.warning,
                subtitle: overview == null
                    ? null
                    : '${formatCount(overview.offersRedemptions)} redeemed  •  ${formatCount(overview.offersActive)} active',
              ),
            ],
          ),
          const SizedBox(height: 24),

          if (overview != null) _ChartsSection(overview: overview),
          segmentsAsync.maybeWhen(
            data: (segments) {
              final shown = segments.segments.where((s) => s.customers > 0).toList();
              if (shown.isEmpty) return const SizedBox.shrink();
              return Padding(
                padding: const EdgeInsets.only(top: 16),
                child: _ChartCard(
                  title: 'Customer segments',
                  subtitle: '${formatCount(segments.totalCustomers)} customers grouped by RFM score - see the Segments page',
                  child: Column(
                    children: [
                      for (final s in shown)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: Row(
                            children: [
                              SizedBox(width: 160, child: Text(s.name, overflow: TextOverflow.ellipsis)),
                              Expanded(
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(4),
                                  child: LinearProgressIndicator(
                                    value: s.share.clamp(0.0, 1.0).toDouble(),
                                    minHeight: 8,
                                    backgroundColor: segmentColor(s.key).withValues(alpha: 0.12),
                                    valueColor: AlwaysStoppedAnimation<Color>(segmentColor(s.key)),
                                  ),
                                ),
                              ),
                              SizedBox(width: 64, child: Text(formatCount(s.customers), textAlign: TextAlign.right)),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
              );
            },
            orElse: () => const SizedBox.shrink(),
          ),
          if (overview == null && overviewAsync.isLoading) const LoadingState(message: 'Loading analytics...'),
        ],
      ),
    );
  }
}

class _ChartsSection extends StatelessWidget {
  const _ChartsSection({required this.overview});

  final DashboardOverview overview;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    final activity = _ChartCard(
      title: 'Customer activity — last 14 days',
      subtitle: '${formatCount(overview.events7d)} events in the last 7 days  •  '
          '${formatCount(overview.purchases30d)} purchases in 30 days',
      child: DailyBars(data: overview.eventsByDay),
    );

    final side = Column(
      children: [
        _ChartCard(
          title: 'Events by type (30 days)',
          child: overview.eventsByType.isEmpty
              ? Text('No events yet.', style: textTheme.bodyMedium)
              : RankedBars(items: overview.eventsByType, labelBuilder: humanize),
        ),
        const SizedBox(height: 16),
        _ChartCard(
          title: 'Top categories (30 days)',
          child: overview.topCategories.isEmpty
              ? Text('No category activity yet.', style: textTheme.bodyMedium)
              : RankedBars(items: overview.topCategories, color: AppColors.success),
        ),
      ],
    );

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= 900) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(flex: 3, child: activity),
              const SizedBox(width: 16),
              Expanded(flex: 2, child: side),
            ],
          );
        }
        return Column(children: [activity, const SizedBox(height: 16), side]);
      },
    );
  }
}

class _ChartCard extends StatelessWidget {
  const _ChartCard({required this.title, required this.child, this.subtitle});

  final String title;
  final String? subtitle;
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
              const SizedBox(height: 16),
              child,
            ],
          ),
        ),
      ),
    );
  }
}

class _SystemStatusBanner extends StatelessWidget {
  const _SystemStatusBanner({required this.healthAsync});

  final AsyncValue<SystemHealthStatus> healthAsync;

  @override
  Widget build(BuildContext context) {
    return healthAsync.when(
      loading: () => const Card(child: Padding(padding: EdgeInsets.all(16), child: LoadingState(message: 'Checking system health...'))),
      error: (err, _) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              const Icon(Icons.error_outline, color: AppColors.danger),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Could not reach the backend at the configured API URL. '
                  'Check that the server is running and API_BASE_URL is correct.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ),
      ),
      data: (health) {
        final isReady = health.status == 'ready';
        final color = isReady ? AppColors.success : AppColors.warning;
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Icon(isReady ? Icons.check_circle : Icons.warning_amber_rounded, color: color),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        isReady ? 'All systems operational' : 'System degraded',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        health.checks.entries.map((e) => '${e.key}: ${e.value}').join('  •  '),
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
