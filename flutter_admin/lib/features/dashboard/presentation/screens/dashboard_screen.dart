import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/utils/responsive.dart';
import '../../../../core/widgets/server_config_dialog.dart';
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
    final userName = authState is AuthAuthenticated ? authState.user.fullName : 'Admin';
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return SingleChildScrollView(
      physics: const BouncingScrollPhysics(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Modern Hero Welcome Banner
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 20),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: isDark
                    ? [
                        const Color(0xFF1E1B4B).withValues(alpha: 0.8),
                        AppColors.cardDark,
                      ]
                    : [
                        const Color(0xFFEEF2FF),
                        Colors.white,
                      ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                color: isDark ? AppColors.primary.withValues(alpha: 0.25) : AppColors.borderLight,
              ),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Wrap(
                        crossAxisAlignment: WrapCrossAlignment.center,
                        spacing: 8,
                        children: [
                          Text(
                            'Welcome back, $userName',
                            style: (Responsive.isMobile(context)
                                    ? Theme.of(context).textTheme.titleLarge
                                    : Theme.of(context).textTheme.headlineSmall)
                                ?.copyWith(
                              fontWeight: FontWeight.w800,
                              letterSpacing: -0.4,
                            ),
                          ),
                          const Text('👋', style: TextStyle(fontSize: 20)),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'AI Personalization & Recommendation Engine is active with live Welfog Store data.',
                        style: TextStyle(
                          fontSize: 13.5,
                          color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
                if (!Responsive.isMobile(context))
                  FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    ),
                    icon: const Icon(Icons.refresh_rounded, size: 18),
                    label: const Text('Refresh Data'),
                    onPressed: () {
                      ref.invalidate(dashboardOverviewProvider);
                      ref.invalidate(systemHealthProvider);
                      ref.invalidate(segmentOverviewProvider);
                    },
                  ),
              ],
            ),
          ),
          const SizedBox(height: 20),

          // System Health & Engine Status
          _SystemStatusBanner(healthAsync: healthAsync),
          const SizedBox(height: 24),

          // Section Header
          Row(
            children: [
              Expanded(
                child: Text(
                  'Store Overview & Metrics',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.3,
                      ),
                ),
              ),
              if (Responsive.isMobile(context))
                IconButton(
                  tooltip: 'Refresh',
                  icon: const Icon(Icons.refresh_rounded),
                  onPressed: () {
                    ref.invalidate(dashboardOverviewProvider);
                    ref.invalidate(systemHealthProvider);
                  },
                ),
            ],
          ),
          const SizedBox(height: 12),

          if (overviewAsync.hasError && overview == null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(errorMessageOf(overviewAsync.error!), style: Theme.of(context).textTheme.bodyMedium),
            ),

          // Fully Responsive Adaptive KPI Cards Grid (Zero-assertion safe on Android / Web / Desktop)
          LayoutBuilder(
            builder: (context, constraints) {
              if (constraints.maxWidth <= 0) {
                return const SizedBox.shrink();
              }
              final width = constraints.maxWidth;
              final crossAxisCount = width < 540 ? 1 : (width < 960 ? 2 : 4);
              final cardWidth = (width - (crossAxisCount - 1) * 16) / crossAxisCount;

              final cards = [
                KpiCard(
                  label: 'Total Customers',
                  value: overview == null ? '—' : formatCount(overview.customers),
                  icon: Icons.people_alt_rounded,
                  accentColor: AppColors.primary,
                  subtitle: 'Verified shoppers & registered buyers',
                ),
                KpiCard(
                  label: 'Catalogue Products',
                  value: overview == null ? '—' : formatCount(overview.products),
                  icon: Icons.inventory_2_rounded,
                  accentColor: AppColors.info,
                  subtitle: overview == null ? null : '${formatCount(overview.activeProducts)} in-stock & active',
                ),
                KpiCard(
                  label: 'Recommendations',
                  value: overview == null ? '—' : formatCount(overview.recommendationsServed),
                  icon: Icons.auto_awesome_rounded,
                  accentColor: AppColors.success,
                  subtitle: overview == null
                      ? null
                      : '${formatCount(overview.recommendationsServed7d)} served in 7d  •  CTR ${formatPercent(overview.ctr)}',
                ),
                KpiCard(
                  label: 'Offers & Coupons',
                  value: overview == null ? '—' : formatCount(overview.offersImpressions),
                  icon: Icons.local_offer_rounded,
                  accentColor: AppColors.warning,
                  subtitle: overview == null
                      ? null
                      : '${formatCount(overview.offersRedemptions)} redeemed  •  ${formatCount(overview.offersActive)} active coupon',
                ),
              ];

              return Wrap(
                spacing: 16,
                runSpacing: 16,
                children: [
                  for (final card in cards)
                    SizedBox(
                      width: cardWidth,
                      height: 160,
                      child: card,
                    ),
                ],
              );
            },
          ),
          const SizedBox(height: 24),

          // Charts Section
          if (overview != null) _ChartsSection(overview: overview),

          // Customer Segments Progress Bar Card
          segmentsAsync.maybeWhen(
            data: (segments) {
              final shown = segments.segments.where((s) => s.customers > 0).toList();
              if (shown.isEmpty) return const SizedBox.shrink();
              return Padding(
                padding: const EdgeInsets.only(top: 16),
                child: _ChartCard(
                  title: 'Customer Segments Distribution (RFM)',
                  subtitle: '${formatCount(segments.totalCustomers)} customers grouped into dynamic behavior clusters',
                  child: Column(
                    children: [
                      for (final s in shown)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: Row(
                            children: [
                              SizedBox(
                                width: Responsive.isMobile(context) ? 110 : 160,
                                child: Text(
                                  s.name,
                                  style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              Expanded(
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(6),
                                  child: LinearProgressIndicator(
                                    value: s.share.clamp(0.0, 1.0).toDouble(),
                                    minHeight: 10,
                                    backgroundColor: segmentColor(s.key).withValues(alpha: 0.12),
                                    valueColor: AlwaysStoppedAnimation<Color>(segmentColor(s.key)),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              SizedBox(
                                width: 50,
                                child: Text(
                                  formatCount(s.customers),
                                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                                  textAlign: TextAlign.right,
                                ),
                              ),
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
          if (overview == null && overviewAsync.isLoading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 40),
              child: LoadingState(message: 'Loading store intelligence...'),
            ),
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
      title: 'Customer Activity — Last 14 Days',
      subtitle: '${formatCount(overview.events7d)} events in the last 7 days  •  '
          '${formatCount(overview.purchases30d)} purchases in 30 days',
      child: DailyBars(data: overview.eventsByDay),
    );

    final side = Column(
      children: [
        _ChartCard(
          title: 'Events by Type (30 Days)',
          child: overview.eventsByType.isEmpty
              ? Text('No events yet.', style: textTheme.bodyMedium)
              : RankedBars(items: overview.eventsByType, labelBuilder: humanize),
        ),
        const SizedBox(height: 16),
        _ChartCard(
          title: 'Top Performing Categories',
          child: overview.topCategories.isEmpty
              ? Text('No category activity yet.', style: textTheme.bodyMedium)
              : RankedBars(items: overview.topCategories, color: AppColors.success),
        ),
      ],
    );

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= 940) {
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
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: isDark ? AppColors.borderDark : AppColors.borderLight,
        ),
      ),
      child: SizedBox(
        width: double.infinity,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
              ),
              if (subtitle != null) ...[
                const SizedBox(height: 4),
                Text(
                  subtitle!,
                  style: TextStyle(
                    fontSize: 12.5,
                    color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
                  ),
                ),
              ],
              const SizedBox(height: 18),
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
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return healthAsync.when(
      loading: () => Card(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        child: const Padding(padding: EdgeInsets.all(16), child: LoadingState(message: 'Checking engine health...')),
      ),
      error: (err, _) => Card(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        color: AppColors.danger.withValues(alpha: isDark ? 0.15 : 0.08),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              const Icon(Icons.error_outline_rounded, color: AppColors.danger),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Could not reach backend API at configured URL. Check Docker backend container or tap to change server address.',
                  style: TextStyle(color: isDark ? Colors.white : AppColors.danger, fontSize: 13),
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.danger,
                  side: BorderSide(color: AppColors.danger.withValues(alpha: 0.5)),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  visualDensity: VisualDensity.compact,
                ),
                icon: const Icon(Icons.settings_ethernet_rounded, size: 16),
                label: const Text('Server Settings', style: TextStyle(fontSize: 12)),
                onPressed: () => showServerConfigDialog(context),
              ),
            ],
          ),
        ),
      ),
      data: (health) {
        final isReady = health.status == 'ready';
        final color = isReady ? AppColors.success : AppColors.warning;

        return Card(
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: BorderSide(
              color: isReady
                  ? AppColors.success.withValues(alpha: isDark ? 0.25 : 0.35)
                  : AppColors.warning.withValues(alpha: 0.35),
            ),
          ),
          color: isReady
              ? AppColors.success.withValues(alpha: isDark ? 0.08 : 0.04)
              : AppColors.warning.withValues(alpha: isDark ? 0.08 : 0.04),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(
                    isReady ? Icons.check_circle_rounded : Icons.warning_amber_rounded,
                    color: color,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        isReady ? 'All AI Engine Systems Operational' : 'System Degraded',
                        style: TextStyle(
                          color: isDark ? Colors.white : AppColors.textPrimaryLight,
                          fontWeight: FontWeight.w700,
                          fontSize: 14.5,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        health.checks.entries.map((e) => '${e.key}: ${e.value}').join('  •  '),
                        style: TextStyle(
                          fontSize: 12,
                          color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
                        ),
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
