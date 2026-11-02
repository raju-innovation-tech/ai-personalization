import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../domain/recommendation.dart';
import '../providers/recommendations_providers.dart';
import '../widgets/recommendation_tile.dart';

enum _Mode { forUser, similar, together, popular }

extension on _Mode {
  String get label {
    switch (this) {
      case _Mode.forUser:
        return 'For a customer';
      case _Mode.similar:
        return 'Similar products';
      case _Mode.together:
        return 'Bought together';
      case _Mode.popular:
        return 'Popular';
    }
  }

  String get inputLabel {
    switch (this) {
      case _Mode.forUser:
        return 'Customer ID';
      case _Mode.similar:
      case _Mode.together:
        return 'Product ID';
      case _Mode.popular:
        return 'Category (optional)';
    }
  }

  String get sample {
    switch (this) {
      case _Mode.forUser:
        return 'USER_10005';
      case _Mode.similar:
      case _Mode.together:
        return 'PROD_1010';
      case _Mode.popular:
        return '';
    }
  }
}

class RecommendationsScreen extends ConsumerStatefulWidget {
  const RecommendationsScreen({super.key});

  @override
  ConsumerState<RecommendationsScreen> createState() => _RecommendationsScreenState();
}

class _RecommendationsScreenState extends ConsumerState<RecommendationsScreen> {
  final TextEditingController _input = TextEditingController(text: _Mode.forUser.sample);
  _Mode _mode = _Mode.forUser;
  Future<RecommendationResult>? _future;
  bool _rebuilding = false;

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  void _selectMode(_Mode mode) {
    setState(() {
      _mode = mode;
      _input.text = mode.sample;
      _future = null;
    });
  }

  Future<RecommendationResult> _fetch() {
    final repository = ref.read(recommendationsRepositoryProvider);
    final id = _input.text.trim();
    switch (_mode) {
      case _Mode.forUser:
        return repository.forUser(id);
      case _Mode.similar:
        return repository.similar(id);
      case _Mode.together:
        return repository.frequentlyBought(id);
      case _Mode.popular:
        return repository.popular(category: id);
    }
  }

  void _run() {
    if (_mode != _Mode.popular && _input.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Enter a ${_mode.inputLabel.toLowerCase()} first.')));
      return;
    }
    final future = _fetch();
    setState(() {
      _future = future;
    });
    // Refresh the usage counters once the call has been served (or failed).
    future.whenComplete(() {
      if (mounted) ref.invalidate(recommendationStatusProvider);
    }).ignore();
  }

  Future<void> _rebuildModel() async {
    setState(() => _rebuilding = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(recommendationsRepositoryProvider).refresh();
      ref.invalidate(recommendationStatusProvider);
      messenger.showSnackBar(const SnackBar(content: Text('Recommendation model rebuilt.')));
    } catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(errorMessageOf(error))));
    } finally {
      if (mounted) setState(() => _rebuilding = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final statusAsync = ref.watch(recommendationStatusProvider);

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Recommendation Engine', style: textTheme.headlineSmall),
          const SizedBox(height: 4),
          Text(
            'Popularity, content similarity, collaborative filtering, bought-together and a personalised hybrid.',
            style: textTheme.bodyMedium,
          ),
          const SizedBox(height: 20),
          _StatusCard(statusAsync: statusAsync, rebuilding: _rebuilding, onRebuild: _rebuildModel),
          const SizedBox(height: 20),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Try it out', style: textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text('Run the same API your storefront calls and see why each product was picked.',
                      style: textTheme.bodyMedium),
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final mode in _Mode.values)
                        ChoiceChip(
                          label: Text(mode.label),
                          selected: _mode == mode,
                          onSelected: (_) => _selectMode(mode),
                        ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      SizedBox(
                        width: 280,
                        child: TextField(
                          controller: _input,
                          onSubmitted: (_) => _run(),
                          decoration: InputDecoration(labelText: _mode.inputLabel, isDense: true),
                        ),
                      ),
                      FilledButton.icon(
                        onPressed: _run,
                        icon: const Icon(Icons.play_arrow_rounded, size: 20),
                        label: const Text('Get recommendations'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  _ResultView(future: _future),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.statusAsync, required this.rebuilding, required this.onRebuild});

  final AsyncValue<EngineStatus> statusAsync;
  final bool rebuilding;
  final VoidCallback onRebuild;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: statusAsync.when(
          loading: () => const Padding(padding: EdgeInsets.all(12), child: LoadingState(message: 'Loading engine status...')),
          error: (error, _) => Row(
            children: [
              const Icon(Icons.error_outline, color: AppColors.danger),
              const SizedBox(width: 12),
              Expanded(child: Text(errorMessageOf(error), style: textTheme.bodyMedium)),
            ],
          ),
          data: (status) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text('Engine status', style: textTheme.titleMedium)),
                  OutlinedButton.icon(
                    onPressed: rebuilding ? null : onRebuild,
                    icon: rebuilding
                        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.refresh, size: 18),
                    label: const Text('Rebuild model'),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                'Model built ${formatTimestamp(status.builtAt)} from the last ${status.lookbackDays} days of behaviour.',
                style: textTheme.bodyMedium,
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  _Stat('Products', formatCount(status.products)),
                  _Stat('Customers with history', formatCount(status.customersWithHistory)),
                  _Stat('Interactions', formatCount(status.interactions)),
                  _Stat('Purchase baskets', formatCount(status.baskets)),
                  _Stat('Bought-together pairs', formatCount(status.fbtPairs)),
                  _Stat('Served (7 days)', formatCount(status.served7d)),
                  _Stat('Served (all time)', formatCount(status.servedTotal)),
                ],
              ),
              if (status.servedByAlgorithm.isNotEmpty) ...[
                const SizedBox(height: 14),
                Text('Usage by algorithm', style: textTheme.bodyMedium),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final entry in status.servedByAlgorithm.entries)
                      Chip(
                        visualDensity: VisualDensity.compact,
                        label: Text('${algorithmLabel(entry.key)}: ${formatCount(entry.value.total)}'),
                      ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Container(
      width: 150,
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

class _ResultView extends StatelessWidget {
  const _ResultView({required this.future});

  final Future<RecommendationResult>? future;

  @override
  Widget build(BuildContext context) {
    if (future == null) {
      return Text('Pick a mode, enter an ID and press the button.', style: Theme.of(context).textTheme.bodyMedium);
    }
    return FutureBuilder<RecommendationResult>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator(strokeWidth: 2.5)));
        }
        if (snapshot.hasError) {
          return Row(
            children: [
              const Icon(Icons.error_outline, color: AppColors.danger, size: 20),
              const SizedBox(width: 8),
              Expanded(child: Text(errorMessageOf(snapshot.error!), style: Theme.of(context).textTheme.bodyMedium)),
            ],
          );
        }
        final result = snapshot.data!;
        final personalized = result.personalized;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 4,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text('${result.items.length} results', style: Theme.of(context).textTheme.titleMedium),
                AlgorithmChip(result.algorithm),
                if (personalized == false)
                  Text('No history for this customer yet, showing what is popular.',
                      style: Theme.of(context).textTheme.bodyMedium),
              ],
            ),
            const SizedBox(height: 8),
            if (result.items.isEmpty)
              Text('Nothing to recommend.', style: Theme.of(context).textTheme.bodyMedium)
            else
              for (var i = 0; i < result.items.length; i++) ...[
                if (i > 0) const Divider(height: 1),
                RecommendationTile(item: result.items[i], rank: i + 1),
              ],
          ],
        );
      },
    );
  }
}
