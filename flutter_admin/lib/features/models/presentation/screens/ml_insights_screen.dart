import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../domain/ml_models.dart';
import '../providers/ml_providers.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Screen
// ─────────────────────────────────────────────────────────────────────────────

class MlInsightsScreen extends ConsumerStatefulWidget {
  const MlInsightsScreen({super.key});

  @override
  ConsumerState<MlInsightsScreen> createState() => _MlInsightsScreenState();
}

class _MlInsightsScreenState extends ConsumerState<MlInsightsScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tab;
  bool _rebuilding = false;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() {
    _tab.dispose();
    super.dispose();
  }

  Future<void> _rebuild() async {
    setState(() => _rebuilding = true);
    try {
      await ref.read(mlRepositoryProvider).rebuild();
      if (mounted) {
        ref.invalidate(mlModelsProvider);
        ref.invalidate(mlTopChurnProvider);
        ref.invalidate(mlTopPurchaseProvider);
        ref.invalidate(mlChurnDistributionProvider);
        ref.invalidate(mlPurchaseDistributionProvider);
        ref.invalidate(mlRebuildProvider);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('ML models rebuilt successfully'),
            backgroundColor: AppColors.success,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Rebuild failed: ${errorMessageOf(e)}'), backgroundColor: AppColors.danger),
        );
      }
    } finally {
      if (mounted) setState(() => _rebuilding = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // ── Header ─────────────────────────────────────────────────────────
        Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF7C3AED), Color(0xFF4F46E5)],
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.psychology_rounded, color: Colors.white, size: 24),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'ML Insights',
                    style: Theme.of(context)
                        .textTheme
                        .headlineSmall
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  Text(
                    'Purchase probability · Churn risk · Offer response',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: isDark
                              ? AppColors.textSecondaryDark
                              : AppColors.textSecondaryLight,
                        ),
                  ),
                ],
              ),
            ),
            _RebuildButton(rebuilding: _rebuilding, onTap: _rebuild),
          ],
        ),
        const SizedBox(height: 20),

        // ── Model status cards ──────────────────────────────────────────────
        _ModelStatusRow(),
        const SizedBox(height: 20),

        // ── Tab bar ────────────────────────────────────────────────────────
        Container(
          decoration: BoxDecoration(
            color: isDark ? AppColors.cardDark : AppColors.cardLight,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: isDark ? AppColors.borderDark : AppColors.borderLight,
            ),
          ),
          child: TabBar(
            controller: _tab,
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            indicator: BoxDecoration(
              color: AppColors.primary.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(10),
            ),
            indicatorSize: TabBarIndicatorSize.tab,
            dividerColor: Colors.transparent,
            labelColor: AppColors.primary,
            unselectedLabelColor: isDark
                ? AppColors.textSecondaryDark
                : AppColors.textSecondaryLight,
            labelStyle:
                const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
            tabs: const [
              Tab(text: 'Churn Risk'),
              Tab(text: 'Purchase Probability'),
              Tab(text: 'Score Distribution'),
              Tab(text: 'Playground'),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // ── Tab views ──────────────────────────────────────────────────────
        Expanded(
          child: TabBarView(
            controller: _tab,
            children: const [
              _ChurnRiskTab(),
              _PurchaseProbabilityTab(),
              _DistributionTab(),
              _PlaygroundTab(),
            ],
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Rebuild button
// ─────────────────────────────────────────────────────────────────────────────

class _RebuildButton extends StatelessWidget {
  const _RebuildButton({required this.rebuilding, required this.onTap});

  final bool rebuilding;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
      style: FilledButton.styleFrom(
        backgroundColor: const Color(0xFF7C3AED),
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
      onPressed: rebuilding ? null : onTap,
      icon: rebuilding
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
            )
          : const Icon(Icons.refresh_rounded, size: 18),
      label: Text(rebuilding ? 'Rebuilding…' : 'Rebuild Models'),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Model status row
// ─────────────────────────────────────────────────────────────────────────────

class _ModelStatusRow extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(mlModelsProvider);
    return async.when(
      loading: () => const SizedBox(
        height: 100,
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => _ErrorCard(message: e.toString()),
      data: (models) {
        if (models.isEmpty) {
          return const _EmptyCard(
            icon: Icons.psychology_outlined,
            message: 'No models scored yet — tap Rebuild Models to run scoring.',
          );
        }
        return SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: models
                .map((m) => Padding(
                      padding: const EdgeInsets.only(right: 12),
                      child: _ModelCard(model: m),
                    ))
                .toList(),
          ),
        );
      },
    );
  }
}

class _ModelCard extends StatelessWidget {
  const _ModelCard({required this.model});

  final MlModelInfo model;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final names = {
      'purchase_probability': ('Purchase Probability', Icons.shopping_cart_checkout_rounded, AppColors.success),
      'churn_risk': ('Churn Risk', Icons.warning_amber_rounded, AppColors.danger),
      'offer_response': ('Offer Response', Icons.local_offer_rounded, AppColors.info),
    };
    final (label, icon, color) = names[model.name] ?? (model.name, Icons.model_training_rounded, AppColors.primary);

    final fmt = NumberFormat.compact();
    return Container(
      width: 220,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? AppColors.cardDark : AppColors.cardLight,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: color.withValues(alpha: 0.3),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: isDark ? 0.05 : 0.08),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(icon, size: 18, color: color),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _StatRow(label: 'Customers', value: fmt.format(model.customerCount)),
          _StatRow(label: 'Est. AUC', value: model.estimatedAuc.toStringAsFixed(3)),
          _StatRow(label: 'High risk', value: fmt.format(model.highRiskCount)),
          _StatRow(label: 'Avg score', value: '${(model.avgScore * 100).toStringAsFixed(1)}%'),
          const SizedBox(height: 4),
          Text(
            'v${model.version} · rebuilt',
            style: TextStyle(
              fontSize: 10,
              color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
            ),
          ),
        ],
      ),
    );
  }
}

class _StatRow extends StatelessWidget {
  const _StatRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                fontSize: 11,
                color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
              ),
            ),
          ),
          Text(
            value,
            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Churn Risk Tab
// ─────────────────────────────────────────────────────────────────────────────

class _ChurnRiskTab extends ConsumerWidget {
  const _ChurnRiskTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(mlTopChurnProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => _ErrorCard(message: e.toString()),
      data: (customers) {
        if (customers.isEmpty) {
          return const _EmptyCard(
            icon: Icons.verified_user_outlined,
            message:
                'No high-churn-risk customers found. Run "Rebuild Models" first.',
          );
        }
        return _RiskList(
          customers: customers,
          title: 'Top Churn Risk Customers',
          subtitle: 'Customers most likely to have churned — target them with win-back offers',
          colorHigh: AppColors.danger,
          colorMedium: AppColors.warning,
          colorLow: AppColors.success,
        );
      },
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Purchase Probability Tab
// ─────────────────────────────────────────────────────────────────────────────

class _PurchaseProbabilityTab extends ConsumerWidget {
  const _PurchaseProbabilityTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(mlTopPurchaseProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => _ErrorCard(message: e.toString()),
      data: (customers) {
        if (customers.isEmpty) {
          return const _EmptyCard(
            icon: Icons.shopping_cart_outlined,
            message:
                'No high-probability buyers found. Run "Rebuild Models" first.',
          );
        }
        return _RiskList(
          customers: customers,
          title: 'Top Purchase Probability Customers',
          subtitle: 'Customers most likely to buy in the next 30 days — great time to show an offer',
          colorHigh: AppColors.success,
          colorMedium: AppColors.info,
          colorLow: isDarkMode(context) ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
        );
      },
    );
  }

  bool isDarkMode(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark;
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared risk list widget
// ─────────────────────────────────────────────────────────────────────────────

class _RiskList extends StatelessWidget {
  const _RiskList({
    required this.customers,
    required this.title,
    required this.subtitle,
    required this.colorHigh,
    required this.colorMedium,
    required this.colorLow,
  });

  final List<TopRiskCustomer> customers;
  final String title;
  final String subtitle;
  final Color colorHigh;
  final Color colorMedium;
  final Color colorLow;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(height: 4),
        Text(
          subtitle,
          style: TextStyle(
            fontSize: 12,
            color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
          ),
        ),
        const SizedBox(height: 12),
        Expanded(
          child: ListView.separated(
            itemCount: customers.length,
            separatorBuilder: (_, __) => const SizedBox(height: 6),
            itemBuilder: (context, i) {
              final c = customers[i];
              final color = c.label == 'high'
                  ? colorHigh
                  : c.label == 'medium'
                      ? colorMedium
                      : colorLow;
              return Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: isDark ? AppColors.cardDark : AppColors.cardLight,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: isDark ? AppColors.borderDark : AppColors.borderLight,
                  ),
                ),
                child: Row(
                  children: [
                    // Rank badge
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Center(
                        child: Text(
                          '#${i + 1}',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: color,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            c.userId,
                            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                          ),
                          Text(
                            c.explanation,
                            style: TextStyle(
                              fontSize: 11,
                              color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          '${(c.score * 100).toStringAsFixed(0)}%',
                          style: TextStyle(
                            fontWeight: FontWeight.w800,
                            fontSize: 16,
                            color: color,
                          ),
                        ),
                        _RiskBadge(label: c.label, color: color),
                      ],
                    ),
                    // Score bar
                    const SizedBox(width: 10),
                    SizedBox(
                      width: 60,
                      child: _ScoreBar(score: c.score, color: color),
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _RiskBadge extends StatelessWidget {
  const _RiskBadge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label.toUpperCase(),
        style: TextStyle(fontSize: 9, fontWeight: FontWeight.w700, color: color),
      ),
    );
  }
}

class _ScoreBar extends StatelessWidget {
  const _ScoreBar({required this.score, required this.color});

  final double score;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: LinearProgressIndicator(
        value: score.clamp(0.0, 1.0),
        backgroundColor: isDark ? AppColors.borderDark : AppColors.borderLight,
        valueColor: AlwaysStoppedAnimation<Color>(color),
        minHeight: 6,
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Score Distribution Tab
// ─────────────────────────────────────────────────────────────────────────────

class _DistributionTab extends ConsumerStatefulWidget {
  const _DistributionTab();

  @override
  ConsumerState<_DistributionTab> createState() => _DistributionTabState();
}

class _DistributionTabState extends ConsumerState<_DistributionTab> {
  String _model = 'churn';

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final async = _model == 'churn'
        ? ref.watch(mlChurnDistributionProvider)
        : ref.watch(mlPurchaseDistributionProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              'Score Distribution',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(width: 16),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'churn', label: Text('Churn Risk')),
                ButtonSegment(value: 'purchase', label: Text('Purchase')),
              ],
              selected: {_model},
              onSelectionChanged: (s) => setState(() => _model = s.first),
              style: SegmentedButton.styleFrom(
                selectedBackgroundColor: AppColors.primary.withValues(alpha: 0.15),
                selectedForegroundColor: AppColors.primary,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Expanded(
          child: async.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => _ErrorCard(message: e.toString()),
            data: (dist) {
              if (dist.totalScored == 0) {
                return const _EmptyCard(
                  icon: Icons.bar_chart_outlined,
                  message: 'No scores yet — run Rebuild Models first.',
                );
              }
              final entries = dist.distribution.entries.toList();
              final maxCount = entries.isEmpty
                  ? 1
                  : entries.map((e) => e.value).reduce((a, b) => a > b ? a : b);
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Total scored: ${NumberFormat.compact().format(dist.totalScored)} customers',
                    style: TextStyle(
                      fontSize: 12,
                      color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: isDark ? AppColors.cardDark : AppColors.cardLight,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: isDark ? AppColors.borderDark : AppColors.borderLight,
                        ),
                      ),
                      child: Column(
                        children: [
                          Expanded(
                            child: LayoutBuilder(
                              builder: (context, constraints) {
                                final maxBarH = (constraints.maxHeight - 22).clamp(16.0, 300.0);
                                return Row(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  children: entries.map((entry) {
                                    final ratio = maxCount > 0 ? entry.value / maxCount : 0.0;
                                    final barH = (ratio * maxBarH).clamp(entry.value > 0 ? 4.0 : 0.0, maxBarH);
                                    final bucketPct = int.tryParse(entry.key.split('-').first) ?? 0;
                                    final barColor = bucketPct >= 65
                                        ? (_model == 'churn' ? AppColors.danger : AppColors.success)
                                        : bucketPct >= 35
                                            ? AppColors.warning
                                            : (_model == 'churn' ? AppColors.success : AppColors.danger);
                                    return Expanded(
                                      child: Padding(
                                        padding: const EdgeInsets.symmetric(horizontal: 2),
                                        child: Column(
                                          mainAxisAlignment: MainAxisAlignment.end,
                                          children: [
                                            Text(
                                              entry.value > 0 ? '${entry.value}' : '',
                                              style: const TextStyle(fontSize: 9, fontWeight: FontWeight.w600),
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                            ),
                                            const SizedBox(height: 2),
                                            AnimatedContainer(
                                              duration: const Duration(milliseconds: 600),
                                              curve: Curves.easeOut,
                                              height: barH,
                                              decoration: BoxDecoration(
                                                color: barColor,
                                                borderRadius: BorderRadius.circular(4),
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    );
                                  }).toList(),
                                );
                              },
                            ),
                          ),
                          const SizedBox(height: 6),
                          Row(
                            children: entries.map((entry) {
                              return Expanded(
                                child: Text(
                                  entry.key.replaceAll('%', ''),
                                  style: TextStyle(
                                    fontSize: 8,
                                    color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              );
                            }).toList(),
                          ),
                          const SizedBox(height: 4),
                          const Text(
                            'Score percentile buckets',
                            style: TextStyle(fontSize: 10),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    ),
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

// ─────────────────────────────────────────────────────────────────────────────
// Playground Tab
// ─────────────────────────────────────────────────────────────────────────────

class _PlaygroundTab extends ConsumerStatefulWidget {
  const _PlaygroundTab();

  @override
  ConsumerState<_PlaygroundTab> createState() => _PlaygroundTabState();
}

class _PlaygroundTabState extends ConsumerState<_PlaygroundTab> {
  final _ctrl = TextEditingController();
  String? _lookupId;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Customer ML Profile Lookup',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 4),
        Text(
          'Enter a customer ID to see all three ML predictions for that customer.',
          style: TextStyle(
            fontSize: 12,
            color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
          ),
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _ctrl,
                decoration: InputDecoration(
                  hintText: 'e.g. 1882',
                  prefixIcon: const Icon(Icons.person_search_outlined, size: 18),
                  filled: true,
                  fillColor: isDark ? AppColors.backgroundDark : AppColors.backgroundLight,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: BorderSide(
                      color: isDark ? AppColors.borderDark : AppColors.borderLight,
                    ),
                  ),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                ),
              ),
            ),
            const SizedBox(width: 10),
            FilledButton(
              onPressed: () {
                final id = _ctrl.text.trim();
                if (id.isNotEmpty) setState(() => _lookupId = id);
              },
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF7C3AED),
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              ),
              child: const Text('Look up'),
            ),
          ],
        ),
        const SizedBox(height: 16),
        if (_lookupId != null) Expanded(child: _CustomerProfileView(userId: _lookupId!)),
      ],
    );
  }
}

class _CustomerProfileView extends ConsumerWidget {
  const _CustomerProfileView({required this.userId});

  final String userId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(mlCustomerProfileProvider(userId));
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => _ErrorCard(message: e.toString()),
      data: (profile) {
        if (profile == null) {
          return const _EmptyCard(
            icon: Icons.person_off_outlined,
            message: 'Customer not found or not yet scored. Run "Rebuild Models" first.',
          );
        }
        return SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (profile.purchaseProbability != null)
                _PredictionCard(
                  title: 'Purchase Probability',
                  icon: Icons.shopping_cart_checkout_rounded,
                  pred: profile.purchaseProbability!,
                  accentColor: AppColors.success,
                ),
              const SizedBox(height: 12),
              if (profile.churnRisk != null)
                _PredictionCard(
                  title: 'Churn Risk',
                  icon: Icons.warning_amber_rounded,
                  pred: profile.churnRisk!,
                  accentColor: AppColors.danger,
                  invertColor: true,
                ),
              const SizedBox(height: 12),
              if (profile.offerResponse != null)
                _OfferResponseCard(pred: profile.offerResponse!),
            ],
          ),
        );
      },
    );
  }
}

class _PredictionCard extends StatelessWidget {
  const _PredictionCard({
    required this.title,
    required this.icon,
    required this.pred,
    required this.accentColor,
    this.invertColor = false,
  });

  final String title;
  final IconData icon;
  final CustomerPrediction pred;
  final Color accentColor;
  final bool invertColor;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    // For churn: high score is bad (red); for purchase: high is good (green)
    final displayColor = invertColor
        ? (pred.label == 'high' ? AppColors.danger : pred.label == 'medium' ? AppColors.warning : AppColors.success)
        : (pred.label == 'high' ? AppColors.success : pred.label == 'medium' ? AppColors.info : AppColors.textSecondaryLight);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? AppColors.cardDark : AppColors.cardLight,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: accentColor.withValues(alpha: 0.3), width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 18, color: accentColor),
              const SizedBox(width: 8),
              Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
              const Spacer(),
              Text(
                '${(pred.score * 100).toStringAsFixed(1)}%',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 24, color: displayColor),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: pred.score,
              backgroundColor: isDark ? AppColors.borderDark : AppColors.borderLight,
              valueColor: AlwaysStoppedAnimation<Color>(displayColor),
              minHeight: 8,
            ),
          ),
          const SizedBox(height: 10),
          Text(pred.explanation, style: const TextStyle(fontSize: 13)),
          const SizedBox(height: 4),
          Row(
            children: [
              _RiskBadge(label: pred.label, color: displayColor),
              const SizedBox(width: 8),
              Text(
                'Confidence: ${(pred.confidence * 100).toStringAsFixed(0)}%',
                style: TextStyle(
                  fontSize: 11,
                  color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _OfferResponseCard extends StatelessWidget {
  const _OfferResponseCard({required this.pred});

  final OfferResponsePrediction pred;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final typeInfo = {
      'discount': ('Discount Offer', Icons.discount_outlined, AppColors.info),
      'loyalty_reward': ('Loyalty Reward', Icons.star_rounded, AppColors.warning),
      'win_back': ('Win-back Campaign', Icons.undo_rounded, AppColors.danger),
      'none': ('No Offer Needed', Icons.check_circle_outline_rounded, AppColors.success),
    };
    final (label, icon, color) = typeInfo[pred.recommendedOfferType] ??
        (pred.recommendedOfferType, Icons.local_offer_outlined, AppColors.primary);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? AppColors.cardDark : AppColors.cardLight,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.info.withValues(alpha: 0.3), width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.local_offer_rounded, size: 18, color: AppColors.info),
              const SizedBox(width: 8),
              const Text('Offer Response Prediction',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            ],
          ),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: color.withValues(alpha: 0.25)),
            ),
            child: Row(
              children: [
                Icon(icon, color: color, size: 24),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Recommended: $label',
                        style: TextStyle(fontWeight: FontWeight.w700, color: color),
                      ),
                      Text(pred.explanation, style: const TextStyle(fontSize: 12)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'All offer type scores',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
            ),
          ),
          const SizedBox(height: 6),
          ...pred.scores.entries.map((entry) {
            final pct = entry.value;
            final (entryLabel, _, entryColor) = typeInfo[entry.key] ??
                (entry.key, Icons.circle, AppColors.primary);
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                children: [
                  SizedBox(
                    width: 120,
                    child: Text(entryLabel, style: const TextStyle(fontSize: 11)),
                  ),
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(3),
                      child: LinearProgressIndicator(
                        value: pct.clamp(0.0, 1.0),
                        backgroundColor:
                            isDark ? AppColors.borderDark : AppColors.borderLight,
                        valueColor: AlwaysStoppedAnimation<Color>(entryColor),
                        minHeight: 6,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text('${(pct * 100).toStringAsFixed(0)}%',
                      style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared helpers
// ─────────────────────────────────────────────────────────────────────────────

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: AppColors.danger.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.danger.withValues(alpha: 0.3)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline_rounded, color: AppColors.danger, size: 32),
            const SizedBox(height: 8),
            Text('Error loading ML data', style: const TextStyle(fontWeight: FontWeight.w700)),
            Text(message, style: const TextStyle(fontSize: 12), textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.icon, required this.message});

  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 48,
              color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight),
          const SizedBox(height: 12),
          Text(
            message,
            style: TextStyle(
              color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
