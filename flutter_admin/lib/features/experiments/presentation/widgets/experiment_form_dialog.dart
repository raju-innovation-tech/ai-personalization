import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../domain/experiment.dart';
import '../providers/experiments_providers.dart';

final RegExp _keyPattern = RegExp(r'^[a-z0-9][a-z0-9_-]{2,63}$');

/// Editable copy of one variant (text controllers live here so the list can grow and shrink).
class _VariantDraft {
  _VariantDraft({
    String name = '',
    this.key,
    double weight = 1,
    this.strategy = 'hybrid',
    this.mode = 'all',
    String codes = '',
  })  : name = TextEditingController(text: name),
        weight = TextEditingController(text: weight == weight.roundToDouble() ? weight.toInt().toString() : weight.toString()),
        codes = TextEditingController(text: codes);

  factory _VariantDraft.from(ExperimentVariant variant) {
    final codes = variant.config['offer_codes'];
    return _VariantDraft(
      name: variant.name,
      key: variant.key,
      weight: variant.weight,
      strategy: variant.config['strategy'] as String? ?? 'hybrid',
      mode: codes is List ? (codes.isEmpty ? 'none' : 'only') : 'all',
      codes: codes is List ? codes.join(', ') : '',
    );
  }

  final TextEditingController name;
  final TextEditingController weight;
  final TextEditingController codes;
  String? key;
  String strategy;
  String mode; // offers: all | none | only

  void dispose() {
    name.dispose();
    weight.dispose();
    codes.dispose();
  }

  VariantInput toInput() {
    final codeList = codes.text.split(',').map((c) => c.trim()).where((c) => c.isNotEmpty).toList();
    return VariantInput(
      name: name.text,
      key: key,
      weight: double.tryParse(weight.text.trim()) ?? 1,
      strategy: strategy,
      offerCodes: mode == 'all' ? null : (mode == 'none' ? <String>[] : codeList),
    );
  }
}

/// Create (experiment == null) or edit a draft experiment. Pops `true` when saved.
class ExperimentFormDialog extends ConsumerStatefulWidget {
  const ExperimentFormDialog({super.key, this.experiment});

  final Experiment? experiment;

  @override
  ConsumerState<ExperimentFormDialog> createState() => _ExperimentFormDialogState();
}

class _ExperimentFormDialogState extends ConsumerState<ExperimentFormDialog> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  late final TextEditingController _key;
  late final TextEditingController _name;
  late final TextEditingController _description;
  late final TextEditingController _hypothesis;
  final List<_VariantDraft> _variants = [];

  String _kind = 'recommendations';
  String _metric = 'conversion';
  double _traffic = 100;
  bool _saving = false;
  String? _error;

  bool get _editing => widget.experiment != null;

  @override
  void initState() {
    super.initState();
    final e = widget.experiment;
    _key = TextEditingController(text: e?.key ?? '');
    _name = TextEditingController(text: e?.name ?? '');
    _description = TextEditingController(text: e?.description ?? '');
    _hypothesis = TextEditingController(text: e?.hypothesis ?? '');
    if (e != null) {
      _kind = e.kind;
      _metric = e.primaryMetric;
      _traffic = e.trafficPercent.toDouble();
      _variants.addAll(e.variants.map(_VariantDraft.from));
    } else {
      _variants.addAll([
        _VariantDraft(name: 'Control', key: 'control'),
        _VariantDraft(name: 'Variant B', strategy: 'content'),
      ]);
    }
  }

  @override
  void dispose() {
    for (final controller in [_key, _name, _description, _hypothesis]) {
      controller.dispose();
    }
    for (final variant in _variants) {
      variant.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final input = ExperimentInput(
      key: _key.text,
      name: _name.text,
      description: _description.text,
      hypothesis: _hypothesis.text,
      kind: _kind,
      primaryMetric: _metric,
      trafficPercent: _traffic.round(),
      variants: _variants.map((v) => v.toInput()).toList(),
    );
    try {
      final repository = ref.read(experimentsRepositoryProvider);
      if (_editing) {
        await repository.update(widget.experiment!.id, input);
      } else {
        await repository.create(input);
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = errorMessageOf(error);
      });
    }
  }

  Widget _variantEditor(int index) {
    final draft = _variants[index];
    final textTheme = Theme.of(context).textTheme;
    final isControl = index == 0;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.primary.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(isControl ? 'Control (baseline)' : 'Variant ${index + 1}', style: textTheme.titleMedium?.copyWith(fontSize: 14)),
              ),
              if (_variants.length > 2 && !isControl)
                IconButton(
                  tooltip: 'Remove variant',
                  icon: const Icon(Icons.delete_outline, size: 20),
                  onPressed: _saving
                      ? null
                      : () => setState(() {
                            _variants.removeAt(index).dispose();
                          }),
                ),
            ],
          ),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                flex: 3,
                child: TextFormField(
                  controller: draft.name,
                  enabled: !_saving,
                  decoration: const InputDecoration(labelText: 'Name', isDense: true),
                  validator: (v) => (v ?? '').trim().isEmpty ? 'Name is required' : null,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextFormField(
                  controller: draft.weight,
                  enabled: !_saving,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Weight', isDense: true),
                  validator: (v) {
                    final parsed = double.tryParse((v ?? '').trim());
                    return (parsed == null || parsed <= 0) ? 'Must be > 0' : null;
                  },
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (_kind == 'recommendations')
            InputDecorator(
              decoration: const InputDecoration(
                labelText: 'Recommendation strategy',
                isDense: true,
                contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              ),
              child: DropdownButtonHideUnderline(
                child: DropdownButton<String>(
                  isExpanded: true,
                  isDense: true,
                  value: draft.strategy,
                  items: [
                    for (final strategy in kRecommendationStrategies)
                      DropdownMenuItem(value: strategy, child: Text(strategyLabel(strategy))),
                  ],
                  onChanged: _saving ? null : (value) => setState(() => draft.strategy = value ?? draft.strategy),
                ),
              ),
            )
          else ...[
            InputDecorator(
              decoration: const InputDecoration(
                labelText: 'Which offers do these customers see?',
                isDense: true,
                contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              ),
              child: DropdownButtonHideUnderline(
                child: DropdownButton<String>(
                  isExpanded: true,
                  isDense: true,
                  value: draft.mode,
                  items: const [
                    DropdownMenuItem(value: 'all', child: Text('All offers (normal behaviour)')),
                    DropdownMenuItem(value: 'none', child: Text('No offers (holdout)')),
                    DropdownMenuItem(value: 'only', child: Text('Only specific offers')),
                  ],
                  onChanged: _saving ? null : (value) => setState(() => draft.mode = value ?? draft.mode),
                ),
              ),
            ),
            if (draft.mode == 'only') ...[
              const SizedBox(height: 10),
              TextFormField(
                controller: draft.codes,
                enabled: !_saving,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(labelText: 'Offer codes (comma separated)', hintText: 'COMEBACK20, VIP15', isDense: true),
                validator: (v) => (v ?? '').trim().isEmpty ? 'Enter at least one offer code' : null,
              ),
            ],
          ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Dialog(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 700, maxHeight: 800),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(_editing ? 'Edit experiment' : 'New experiment', style: textTheme.headlineSmall)),
                  IconButton(
                    tooltip: 'Close',
                    icon: const Icon(Icons.close),
                    onPressed: _saving ? null : () => Navigator.of(context).pop(false),
                  ),
                ],
              ),
              Text(
                'The first variant is the control. Customers are assigned once and always see the same variant.',
                style: textTheme.bodyMedium,
              ),
              const SizedBox(height: 12),
              Flexible(
                child: SingleChildScrollView(
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: TextFormField(
                                controller: _key,
                                enabled: !_editing && !_saving,
                                decoration: const InputDecoration(labelText: 'Key', hintText: 'homepage-reco-test', isDense: true),
                                validator: (v) => _keyPattern.hasMatch((v ?? '').trim().toLowerCase())
                                    ? null
                                    : 'Use 3-64 letters, digits, - or _',
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              flex: 2,
                              child: TextFormField(
                                controller: _name,
                                enabled: !_saving,
                                decoration: const InputDecoration(labelText: 'Name', isDense: true),
                                validator: (v) => (v ?? '').trim().isEmpty ? 'Name is required' : null,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _hypothesis,
                          enabled: !_saving,
                          minLines: 1,
                          maxLines: 2,
                          decoration: const InputDecoration(labelText: 'Hypothesis (optional)', hintText: 'We expect ... because ...', isDense: true),
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _description,
                          enabled: !_saving,
                          minLines: 1,
                          maxLines: 2,
                          decoration: const InputDecoration(labelText: 'Description (optional)', isDense: true),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: InputDecorator(
                                decoration: const InputDecoration(
                                  labelText: 'What is tested',
                                  isDense: true,
                                  contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                ),
                                child: DropdownButtonHideUnderline(
                                  child: DropdownButton<String>(
                                    isExpanded: true,
                                    isDense: true,
                                    value: _kind,
                                    items: [
                                      for (final kind in kExperimentKinds)
                                        DropdownMenuItem(value: kind, child: Text(experimentKindLabel(kind))),
                                    ],
                                    onChanged: _saving ? null : (value) => setState(() => _kind = value ?? _kind),
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: InputDecorator(
                                decoration: const InputDecoration(
                                  labelText: 'Primary metric',
                                  isDense: true,
                                  contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                ),
                                child: DropdownButtonHideUnderline(
                                  child: DropdownButton<String>(
                                    isExpanded: true,
                                    isDense: true,
                                    value: _metric,
                                    items: [
                                      for (final metric in kExperimentMetrics)
                                        DropdownMenuItem(value: metric, child: Text(metricLabel(metric), overflow: TextOverflow.ellipsis)),
                                    ],
                                    onChanged: _saving ? null : (value) => setState(() => _metric = value ?? _metric),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Text('Traffic', style: textTheme.titleMedium),
                            const SizedBox(width: 8),
                            Text('${_traffic.round()}% of customers take part', style: textTheme.bodyMedium),
                          ],
                        ),
                        Slider(
                          value: _traffic,
                          min: 1,
                          max: 100,
                          divisions: 99,
                          label: '${_traffic.round()}%',
                          onChanged: _saving ? null : (value) => setState(() => _traffic = value),
                        ),
                        const SizedBox(height: 4),
                        Text('Variants', style: textTheme.titleMedium),
                        const SizedBox(height: 8),
                        for (var i = 0; i < _variants.length; i++) _variantEditor(i),
                        if (_variants.length < 5)
                          Align(
                            alignment: Alignment.centerLeft,
                            child: TextButton.icon(
                              onPressed: _saving
                                  ? null
                                  : () => setState(() => _variants.add(_VariantDraft(name: 'Variant ${_variants.length + 1}'))),
                              icon: const Icon(Icons.add, size: 18),
                              label: const Text('Add variant'),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 8),
                Text(_error!, style: const TextStyle(color: AppColors.danger)),
              ],
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: _saving ? null : () => Navigator.of(context).pop(false),
                    child: const Text('Cancel'),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: _saving ? null : _save,
                    child: _saving
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                        : Text(_editing ? 'Save changes' : 'Create experiment'),
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
