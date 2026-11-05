import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../domain/experiment.dart';
import '../providers/experiments_providers.dart';
import '../widgets/experiment_form_dialog.dart';
import 'experiments_screen.dart';

class ExperimentDetailScreen extends ConsumerWidget {
  const ExperimentDetailScreen({super.key, required this.experimentId});

  final String experimentId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final experimentAsync = ref.watch(experimentDetailProvider(experimentId));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: () => context.go('/experiments'),
            icon: const Icon(Icons.arrow_back, size: 18),
            label: const Text('All experiments'),
          ),
        ),
        Expanded(
          child: experimentAsync.when(
            loading: () => const LoadingState(message: 'Loading experiment...'),
            error: (error, _) => ErrorState(
              message: errorMessageOf(error),
              onRetry: () => ref.invalidate(experimentDetailProvider(experimentId)),
            ),
            data: (experiment) => _Detail(experiment: experiment),
          ),
        ),
      ],
    );
  }
}

class _Detail extends ConsumerWidget {
  const _Detail({required this.experiment});

  final Experiment experiment;

  Future<void> _changeStatus(BuildContext context, WidgetRef ref, String status, {String? winnerKey}) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(experimentsRepositoryProvider).setStatus(experiment.id, status, winnerKey: winnerKey);
      if (context.mounted) refreshExperiments(ref, id: experiment.id);
      messenger.showSnackBar(SnackBar(content: Text('${experiment.name} is now $status.')));
    } catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(errorMessageOf(error))));
    }
  }

  /// Asks which variant (if any) to record as the winner; null = cancelled, '' = no winner.
  Future<String?> _pickWinner(BuildContext context, ExperimentResults? results) {
    final suggested = results?.verdict.winnerKey;
    return showDialog<String>(
      context: context,
      builder: (dialogContext) => SimpleDialog(
        title: const Text('Complete experiment'),
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(24, 0, 24, 8),
            child: Text('Completing stops the test for everyone. Which variant won?'),
          ),
          for (final variant in experiment.variants)
            SimpleDialogOption(
              onPressed: () => Navigator.of(dialogContext).pop(variant.key),
              child: Text(variant.key == suggested ? '${variant.name}  (suggested by the data)' : variant.name),
            ),
          SimpleDialogOption(
            onPressed: () => Navigator.of(dialogContext).pop(''),
            child: const Text('No winner'),
          ),
          SimpleDialogOption(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Cancel'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final resultsAsync = ref.watch(experimentResultsProvider(experiment.id));
    final results = resultsAsync.valueOrNull;
    final status = experiment.status;

    final actions = <Widget>[
      if (status == 'draft') ...[
        FilledButton.icon(
          onPressed: () => _changeStatus(context, ref, 'running'),
          icon: const Icon(Icons.play_arrow_rounded, size: 20),
          label: const Text('Start'),
        ),
        OutlinedButton.icon(
          onPressed: () async {
            final saved = await showDialog<bool>(context: context, builder: (_) => ExperimentFormDialog(experiment: experiment));
            if (saved == true && context.mounted) refreshExperiments(ref, id: experiment.id);
          },
          icon: const Icon(Icons.edit_outlined, size: 18),
          label: const Text('Edit'),
        ),
        OutlinedButton.icon(
          style: OutlinedButton.styleFrom(
            foregroundColor: AppColors.danger,
            side: const BorderSide(color: AppColors.danger),
          ),
          onPressed: () async {
            final messenger = ScaffoldMessenger.of(context);
            final confirmed = await showDialog<bool>(
              context: context,
              builder: (dialogContext) => AlertDialog(
                title: const Text('Delete this draft experiment?'),
                content: Text('Are you sure you want to delete "${experiment.name}"? This action cannot be undone.'),
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
              if (context.mounted) {
                refreshExperiments(ref);
                context.go('/experiments');
                messenger.showSnackBar(
                  SnackBar(
                    content: Text('Experiment "${experiment.name}" deleted successfully.'),
                    backgroundColor: AppColors.success,
                  ),
                );
              }
            } catch (error) {
              messenger.showSnackBar(
                SnackBar(
                  content: Text(errorMessageOf(error)),
                  backgroundColor: AppColors.danger,
                ),
              );
            }
          },
          icon: const Icon(Icons.delete_outline, size: 18),
          label: const Text('Delete'),
        ),
      ],
      if (status == 'running')
        OutlinedButton.icon(
          onPressed: () => _changeStatus(context, ref, 'paused'),
          icon: const Icon(Icons.pause, size: 18),
          label: const Text('Pause'),
        ),
      if (status == 'paused')
        FilledButton.icon(
          onPressed: () => _changeStatus(context, ref, 'running'),
          icon: const Icon(Icons.play_arrow_rounded, size: 20),
          label: const Text('Resume'),
        ),
      if (status == 'running' || status == 'paused')
        OutlinedButton.icon(
          onPressed: () async {
            final winner = await _pickWinner(context, results);
            if (winner == null || !context.mounted) return;
            await _changeStatus(context, ref, 'completed', winnerKey: winner.isEmpty ? null : winner);
          },
          icon: const Icon(Icons.flag_outlined, size: 18),
          label: const Text('Complete'),
        ),
    ];

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 12,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(experiment.name, style: textTheme.headlineSmall),
              StatusPill(status),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '${experiment.key}  •  ${experimentKindLabel(experiment.kind)}  •  primary metric: ${metricLabel(experiment.primaryMetric)}',
            style: textTheme.bodyMedium,
          ),
          if (experiment.hypothesis != null) ...[
            const SizedBox(height: 8),
            Text('Hypothesis: ${experiment.hypothesis}', style: textTheme.bodyLarge),
          ],
          if (experiment.description != null) ...[
            const SizedBox(height: 4),
            Text(experiment.description!, style: textTheme.bodyMedium),
          ],
          const SizedBox(height: 12),
          if (actions.isNotEmpty) Wrap(spacing: 10, runSpacing: 10, children: actions),
          const SizedBox(height: 16),
          resultsAsync.when(
            loading: () => const Padding(padding: EdgeInsets.all(24), child: LoadingState(message: 'Analysing results...')),
            error: (error, _) => ErrorState(
              message: errorMessageOf(error),
              onRetry: () => ref.invalidate(experimentResultsProvider(experiment.id)),
            ),
            data: (data) => _ResultsView(experiment: experiment, results: data),
          ),
          const SizedBox(height: 16),
          _SetupCard(experiment: experiment),
          const SizedBox(height: 16),
          _AssignmentChecker(experimentId: experiment.id),
        ],
      ),
    );
  }
}

class _ResultsView extends StatelessWidget {
  const _ResultsView({required this.experiment, required this.results});

  final Experiment experiment;
  final ExperimentResults results;

  double? _primary(VariantResult v) {
    switch (results.primaryMetric) {
      case 'click':
        return v.clickRate;
      case 'revenue':
        return v.revenuePerCustomer;
      default:
        return v.conversionRate;
    }
  }

  String _formatPrimary(double? value) {
    if (value == null) return '—';
    return results.primaryMetric == 'revenue' ? formatPrice(value) : formatPercent(value);
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final verdict = results.verdict;
    late final Color verdictColor;
    late final IconData verdictIcon;
    switch (verdict.status) {
      case 'winner':
        verdictColor = AppColors.success;
        verdictIcon = Icons.emoji_events_outlined;
      case 'control_better':
        verdictColor = AppColors.info;
        verdictIcon = Icons.shield_outlined;
      case 'inconclusive':
        verdictColor = const Color(0xFF9CA3AF);
        verdictIcon = Icons.hourglass_empty;
      default: // collecting
        verdictColor = AppColors.warning;
        verdictIcon = Icons.hourglass_top;
    }

    final maxRate = results.variants.fold<double>(0, (max, v) {
      final value = _primary(v) ?? 0;
      return value > max ? value : max;
    });

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: verdictColor.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: verdictColor.withValues(alpha: 0.4)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(verdictIcon, color: verdictColor),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      {
                        'winner': 'We have a winner',
                        'control_better': 'The control is better',
                        'inconclusive': 'No clear difference yet',
                      }[verdict.status] ??
                          'Collecting data',
                      style: textTheme.titleMedium,
                    ),
                    const SizedBox(height: 2),
                    Text(verdict.message, style: textTheme.bodyMedium),
                    if (results.neededPerVariant != null && verdict.status == 'inconclusive') ...[
                      const SizedBox(height: 4),
                      Text(
                        'Smallest variant so far: ${formatCount(results.smallestVariant)} customers.',
                        style: textTheme.bodyMedium?.copyWith(fontSize: 12),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        LayoutBuilder(
          builder: (context, constraints) {
            final columns = constraints.maxWidth >= 900 ? results.variants.length.clamp(1, 3).toInt() : 1;
            final width = (constraints.maxWidth - 16 * (columns - 1)) / columns;
            return Wrap(
              spacing: 16,
              runSpacing: 16,
              children: [
                for (final variant in results.variants)
                  SizedBox(
                    width: width,
                    child: _VariantCard(
                      variant: variant,
                      primaryMetric: results.primaryMetric,
                      barValue: maxRate == 0 ? 0.0 : ((_primary(variant) ?? 0) / maxRate).clamp(0.0, 1.0).toDouble(),
                      primaryText: _formatPrimary(_primary(variant)),
                      isWinner: variant.key == experiment.winnerKey || (experiment.status != 'completed' && variant.key == verdict.winnerKey),
                    ),
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _VariantCard extends StatelessWidget {
  const _VariantCard({
    required this.variant,
    required this.primaryMetric,
    required this.primaryText,
    required this.barValue,
    required this.isWinner,
  });

  final VariantResult variant;
  final String primaryMetric;
  final String primaryText;
  final double barValue;
  final bool isWinner;

  Widget _metric(BuildContext context, String metricKey, String label, String value) {
    final textTheme = Theme.of(context).textTheme;
    final comparison = variant.comparisons[metricKey];
    final isPrimary = metricKey == primaryMetric;
    Widget? detail;
    if (comparison != null) {
      final color = comparison.significant ? (comparison.diff > 0 ? AppColors.success : AppColors.danger) : const Color(0xFF9CA3AF);
      detail = Text(
        '${comparison.lift == null ? '' : '${formatChange(comparison.lift)} vs control  •  '}${formatPValue(comparison.pValue)}'
        '${comparison.significant ? '  (significant)' : ''}',
        style: TextStyle(color: color, fontSize: 11.5, fontWeight: FontWeight.w600),
      );
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label + (isPrimary ? '  (primary)' : ''), style: textTheme.bodyMedium?.copyWith(fontSize: 12, fontWeight: isPrimary ? FontWeight.w700 : null)),
          Text(value, style: textTheme.titleMedium?.copyWith(fontSize: isPrimary ? 18 : 15)),
          if (detail != null) detail,
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(variant.name, style: textTheme.titleMedium)),
                if (variant.isControl) const _Tag('Control', AppColors.info),
                if (isWinner) const Padding(padding: EdgeInsets.only(left: 6), child: _Tag('Winner', AppColors.success)),
              ],
            ),
            const SizedBox(height: 4),
            Text('${formatCount(variant.customers)} customers exposed', style: textTheme.bodyMedium?.copyWith(fontSize: 12)),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: barValue,
                minHeight: 8,
                backgroundColor: AppColors.primary.withValues(alpha: 0.12),
                valueColor: AlwaysStoppedAnimation<Color>(isWinner ? AppColors.success : AppColors.primary),
              ),
            ),
            const SizedBox(height: 4),
            _metric(context, 'conversion', 'Purchase conversion', '${formatPercent(variant.conversionRate)}  (${formatCount(variant.conversions)} bought)'),
            _metric(context, 'click', 'Click rate', '${formatPercent(variant.clickRate)}  (${formatCount(variant.clickers)} clicked)'),
            _metric(context, 'revenue', 'Revenue per customer', formatPrice(variant.revenuePerCustomer)),
          ],
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.label, this.color);

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.13), borderRadius: BorderRadius.circular(20)),
      child: Text(label, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w700)),
    );
  }
}

class _SetupCard extends StatelessWidget {
  const _SetupCard({required this.experiment});

  final Experiment experiment;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final small = textTheme.bodyMedium?.copyWith(fontSize: 12);
    return Card(
      child: SizedBox(
        width: double.infinity,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Setup', style: textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(
                '${experiment.trafficPercent}% of customers take part. '
                '${experiment.startedAt == null ? 'Not started yet.' : 'Started ${formatTimestamp(experiment.startedAt!)}.'}'
                '${experiment.endedAt == null ? '' : ' Ended ${formatTimestamp(experiment.endedAt!)}.'}',
                style: textTheme.bodyMedium,
              ),
              const SizedBox(height: 10),
              for (final variant in experiment.variants)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('${variant.name}${variant.isControl ? ' (control)' : ''}', style: textTheme.bodyLarge),
                            Text(variant.describe(experiment.kind), style: small),
                          ],
                        ),
                      ),
                      Text('${(variant.share * 100).round()}% of traffic  •  ${formatCount(variant.exposed)} exposed', style: small),
                    ],
                  ),
                ),
              const SizedBox(height: 8),
              Text(
                'Customers are assigned automatically the first time your site asks for '
                '${experiment.kind == 'offers' ? '/offers/user/{id}' : '/recommendations/user/{id}'} - nothing else to integrate. '
                'Outcomes are counted only after a customer was first shown a variant.',
                style: small,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// "Which variant would customer X get?" - handy for QA; records nothing.
class _AssignmentChecker extends ConsumerStatefulWidget {
  const _AssignmentChecker({required this.experimentId});

  final String experimentId;

  @override
  ConsumerState<_AssignmentChecker> createState() => _AssignmentCheckerState();
}

class _AssignmentCheckerState extends ConsumerState<_AssignmentChecker> {
  final TextEditingController _user = TextEditingController(text: '1882');
  Future<AssignmentPreview>? _future;

  @override
  void dispose() {
    _user.dispose();
    super.dispose();
  }

  void _check() {
    final id = _user.text.trim();
    if (id.isEmpty) return;
    final future = ref.read(experimentsRepositoryProvider).previewAssignment(widget.experimentId, id);
    setState(() {
      _future = future;
    });
  }

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
              Text('Check a customer', style: textTheme.titleMedium),
              const SizedBox(height: 4),
              Text('See which variant a customer would get. This does not record anything.', style: textTheme.bodyMedium),
              const SizedBox(height: 12),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  SizedBox(
                    width: 220,
                    child: TextField(
                      controller: _user,
                      onSubmitted: (_) => _check(),
                      decoration: const InputDecoration(labelText: 'Customer ID', isDense: true),
                    ),
                  ),
                  FilledButton(onPressed: _check, child: const Text('Check')),
                ],
              ),
              const SizedBox(height: 10),
              if (_future != null)
                FutureBuilder<AssignmentPreview>(
                  future: _future,
                  builder: (context, snapshot) {
                    if (snapshot.connectionState != ConnectionState.done) {
                      return const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2));
                    }
                    if (snapshot.hasError) {
                      return Text(errorMessageOf(snapshot.error!), style: textTheme.bodyMedium);
                    }
                    final preview = snapshot.data!;
                    final text = !preview.inExperiment
                        ? 'Not part of this experiment (outside the traffic share).'
                        : 'Variant: ${preview.variant}${preview.alreadyExposed ? '  •  already exposed' : '  •  not exposed yet'}';
                    return Text(text, style: textTheme.bodyLarge);
                  },
                ),
            ],
          ),
        ),
      ),
    );
  }
}
