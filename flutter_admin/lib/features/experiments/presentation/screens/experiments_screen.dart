import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/adaptive_grid.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../../auth/domain/admin_user.dart';
import '../../../auth/presentation/providers/auth_controller.dart';
import '../../../auth/presentation/providers/auth_state.dart';
import '../../domain/experiment.dart';
import '../providers/experiments_providers.dart';
import '../widgets/experiment_form_dialog.dart';

Color experimentStatusColor(String status) {
  switch (status) {
    case 'running':
      return AppColors.success;
    case 'paused':
      return AppColors.warning;
    case 'completed':
      return AppColors.info;
    default: // draft
      return const Color(0xFF9CA3AF);
  }
}

class StatusPill extends StatelessWidget {
  const StatusPill(this.status, {super.key});

  final String status;

  @override
  Widget build(BuildContext context) {
    final color = experimentStatusColor(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.13), borderRadius: BorderRadius.circular(20)),
      child: Text(humanize(status), style: TextStyle(color: color, fontSize: 11.5, fontWeight: FontWeight.w700)),
    );
  }
}

/// Reload everything that shows experiment data.
void refreshExperiments(WidgetRef ref, {String? id}) {
  ref.invalidate(experimentsPageProvider);
  ref.invalidate(experimentStatsProvider);
  if (id != null) {
    ref.invalidate(experimentDetailProvider(id));
    ref.invalidate(experimentResultsProvider(id));
  }
}

class ExperimentsScreen extends ConsumerWidget {
  const ExperimentsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final query = ref.watch(experimentQueryProvider);
    final pageAsync = ref.watch(experimentsPageProvider);
    final statsAsync = ref.watch(experimentStatsProvider);

    const statuses = <(String?, String)>[
      (null, 'All'),
      ('running', 'Running'),
      ('draft', 'Draft'),
      ('paused', 'Paused'),
      ('completed', 'Completed'),
    ];

    Future<void> create() async {
      final saved = await showDialog<bool>(context: context, builder: (_) => const ExperimentFormDialog());
      if (saved == true && context.mounted) refreshExperiments(ref);
    }

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
                    Text('Experiments', style: textTheme.headlineSmall),
                    const SizedBox(height: 4),
                    Text(
                      'A/B tests: show different recommendation strategies or offers to different customers and let the numbers decide.',
                      style: textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              FilledButton.icon(onPressed: create, icon: const Icon(Icons.add, size: 20), label: const Text('New experiment')),
            ],
          ),
          const SizedBox(height: 16),
          statsAsync.maybeWhen(data: (stats) => _StatsStrip(stats: stats), orElse: () => const SizedBox.shrink()),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final entry in statuses)
                ChoiceChip(
                  label: Text(entry.$2),
                  selected: query.status == entry.$1,
                  onSelected: (_) => ref.read(experimentQueryProvider.notifier).state =
                      entry.$1 == null ? query.copyWith(clearStatus: true) : query.copyWith(status: entry.$1),
                ),
            ],
          ),
          const SizedBox(height: 16),
          pageAsync.when(
            loading: () => const Padding(padding: EdgeInsets.all(32), child: LoadingState(message: 'Loading experiments...')),
            error: (error, _) => ErrorState(
              message: errorMessageOf(error),
              onRetry: () => ref.invalidate(experimentsPageProvider),
            ),
            data: (page) {
              if (page.items.isEmpty) {
                return const EmptyState(
                  title: 'No experiments yet',
                  subtitle: 'Create one with the New experiment button.',
                  icon: Icons.science_outlined,
                );
              }
              return Column(
                children: [
                  for (final experiment in page.items) ...[
                    _ExperimentCard(experiment: experiment),
                    const SizedBox(height: 12),
                  ],
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          '${formatCount(page.total)} experiments  •  page ${page.page} of ${page.totalPages}',
                          style: textTheme.bodyMedium,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      IconButton(
                        tooltip: 'Previous page',
                        icon: const Icon(Icons.chevron_left),
                        onPressed: page.page > 1
                            ? () => ref.read(experimentQueryProvider.notifier).state = query.copyWith(page: page.page - 1)
                            : null,
                      ),
                      IconButton(
                        tooltip: 'Next page',
                        icon: const Icon(Icons.chevron_right),
                        onPressed: page.page < page.totalPages
                            ? () => ref.read(experimentQueryProvider.notifier).state = query.copyWith(page: page.page + 1)
                            : null,
                      ),
                    ],
                  ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}

class _StatsStrip extends StatelessWidget {
  const _StatsStrip({required this.stats});

  final ExperimentStatsData stats;

  @override
  Widget build(BuildContext context) {
    final tiles = <(String, String)>[
      ('Running now', formatCount(stats.byStatus['running'] ?? 0)),
      ('Total experiments', formatCount(stats.total)),
      ('Finished (30 days)', formatCount(stats.completed30d)),
      ('Customers in tests', formatCount(stats.exposedCustomers)),
    ];
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: AdaptiveGrid(
        itemMinWidth: 150,
        children: [
          for (final tile in tiles)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: AppColors.primary.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(10)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(tile.$2, style: textTheme.titleMedium),
                  const SizedBox(height: 2),
                  Text(tile.$1, style: textTheme.bodyMedium?.copyWith(fontSize: 12)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _ExperimentCard extends ConsumerWidget {
  const _ExperimentCard({required this.experiment});

  final Experiment experiment;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final small = textTheme.bodyMedium?.copyWith(fontSize: 12);
    final auth = ref.watch(authControllerProvider);
    final user = auth is AuthAuthenticated ? auth.user : null;
    final isSuperAdmin = user?.role == UserRole.superAdmin;
    final isAdmin = user?.role == UserRole.admin;
    final canDelete = isSuperAdmin || (isAdmin && experiment.status == 'draft');

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.go('/experiments/${experiment.id}'),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: Text(experiment.name, style: textTheme.titleMedium)),
                  const SizedBox(width: 8),
                  StatusPill(experiment.status),
                  if (canDelete) ...[
                    const SizedBox(width: 4),
                    PopupMenuButton<String>(
                      tooltip: 'Actions',
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                      icon: const Icon(Icons.more_vert, size: 20),
                      onSelected: (action) async {
                        if (action == 'delete') {
                          final messenger = ScaffoldMessenger.of(context);
                          final confirmed = await showDialog<bool>(
                            context: context,
                            builder: (dialogContext) => AlertDialog(
                              title: const Text('Delete this experiment?'),
                              content: Text('Are you sure you want to permanently delete "${experiment.name}"? This action cannot be undone.'),
                              actions: [
                                TextButton(
                                  onPressed: () => Navigator.of(dialogContext).pop(false),
                                  child: const Text('Cancel'),
                                ),
                                FilledButton(
                                  style: FilledButton.styleFrom(backgroundColor: AppColors.danger),
                                  onPressed: () => Navigator.of(dialogContext).pop(true),
                                  child: const Text('Delete'),
                                ),
                              ],
                            ),
                          );
                          if (confirmed != true || !context.mounted) return;

                          try {
                            await ref.read(experimentsRepositoryProvider).deleteExperiment(experiment.id);
                            if (context.mounted) refreshExperiments(ref);
                            messenger.showSnackBar(
                              SnackBar(
                                content: Text('Experiment "${experiment.name}" deleted successfully.'),
                                backgroundColor: AppColors.success,
                              ),
                            );
                          } catch (error) {
                            messenger.showSnackBar(
                              SnackBar(
                                content: Text(errorMessageOf(error)),
                                backgroundColor: AppColors.danger,
                              ),
                            );
                          }
                        }
                      },
                      itemBuilder: (_) => [
                        const PopupMenuItem(
                          value: 'delete',
                          child: Row(
                            children: [
                              Icon(Icons.delete_outline, size: 18, color: AppColors.danger),
                              SizedBox(width: 8),
                              Text('Delete', style: TextStyle(color: AppColors.danger)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 4),
              Text(
                '${experimentKindLabel(experiment.kind)}  •  ${metricLabel(experiment.primaryMetric)}  •  '
                '${experiment.trafficPercent}% of customers  •  ${formatCount(experiment.exposedTotal)} exposed',
                style: small,
              ),
              const SizedBox(height: 10),
              for (final variant in experiment.variants)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    children: [
                      Icon(
                        variant.key == experiment.winnerKey ? Icons.emoji_events_outlined : Icons.circle,
                        size: variant.key == experiment.winnerKey ? 16 : 7,
                        color: variant.key == experiment.winnerKey ? AppColors.warning : AppColors.primary,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          '${variant.name}${variant.isControl ? ' (control)' : ''} — ${variant.describe(experiment.kind)}',
                          style: textTheme.bodyMedium,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      Text('${(variant.share * 100).round()}%  •  ${formatCount(variant.exposed)}', style: small),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
