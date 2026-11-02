import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../segments/presentation/providers/segments_providers.dart';
import '../../domain/offer.dart';
import '../providers/offers_providers.dart';

final RegExp _codePattern = RegExp(r'^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$');

/// Create (offer == null) or edit an offer. Pops `true` when something was saved.
class OfferFormDialog extends ConsumerStatefulWidget {
  const OfferFormDialog({super.key, this.offer});

  final Offer? offer;

  @override
  ConsumerState<OfferFormDialog> createState() => _OfferFormDialogState();
}

class _OfferFormDialogState extends ConsumerState<OfferFormDialog> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  late final TextEditingController _code;
  late final TextEditingController _name;
  late final TextEditingController _description;
  late final TextEditingController _value;
  late final TextEditingController _maxDiscount;
  late final TextEditingController _minOrder;
  late final TextEditingController _maxRedemptions;
  late final TextEditingController _maxPerCustomer;
  late final TextEditingController _categories;

  String _type = 'percent_off';
  DateTime? _start;
  DateTime? _end;
  final Set<String> _segments = <String>{};
  double _priority = 50;
  bool _saving = false;
  String? _error;

  bool get _editing => widget.offer != null;

  static String _plain(double? value) {
    if (value == null) return '';
    return value == value.roundToDouble() ? value.toInt().toString() : value.toString();
  }

  @override
  void initState() {
    super.initState();
    final offer = widget.offer;
    _code = TextEditingController(text: offer?.code ?? '');
    _name = TextEditingController(text: offer?.name ?? '');
    _description = TextEditingController(text: offer?.description ?? '');
    _value = TextEditingController(text: offer == null ? '10' : _plain(offer.value));
    _maxDiscount = TextEditingController(text: _plain(offer?.maxDiscount));
    _minOrder = TextEditingController(text: _plain(offer?.minOrderValue));
    _maxRedemptions = TextEditingController(text: offer?.maxRedemptions?.toString() ?? '');
    _maxPerCustomer = TextEditingController(text: (offer?.maxPerCustomer ?? 1).toString());
    _categories = TextEditingController(text: (offer?.targetCategories ?? const <String>[]).join(', '));
    if (offer != null) {
      _type = offer.offerType;
      _priority = offer.priority.toDouble();
      _segments.addAll(offer.targetSegments);
      _start = offer.startsAt == null ? null : DateTime.tryParse(offer.startsAt!)?.toLocal();
      _end = offer.endsAt == null ? null : DateTime.tryParse(offer.endsAt!)?.toLocal();
    }
  }

  @override
  void dispose() {
    for (final controller in [
      _code, _name, _description, _value, _maxDiscount, _minOrder, _maxRedemptions, _maxPerCustomer, _categories,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  String? _requiredNumber(String? text, {required double min, double? max, String label = 'Value'}) {
    final parsed = double.tryParse((text ?? '').trim());
    if (parsed == null) return '$label must be a number';
    if (parsed < min || (max != null && parsed > max)) {
      return max == null ? '$label must be at least ${_plain(min)}' : '$label must be between ${_plain(min)} and ${_plain(max)}';
    }
    return null;
  }

  String? _optionalNumber(String? text, {double min = 0}) {
    final trimmed = (text ?? '').trim();
    if (trimmed.isEmpty) return null;
    final parsed = double.tryParse(trimmed);
    if (parsed == null || parsed < min) return 'Enter a number ≥ ${_plain(min)}';
    return null;
  }

  Future<void> _pickDate({required bool start}) async {
    final now = DateTime.now();
    final initial = (start ? _start : _end) ?? now;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2020),
      lastDate: DateTime(2100),
    );
    if (picked == null || !mounted) return;
    setState(() {
      if (start) {
        _start = DateTime(picked.year, picked.month, picked.day);
      } else {
        _end = DateTime(picked.year, picked.month, picked.day, 23, 59, 59);
      }
    });
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (_start != null && _end != null && !_end!.isAfter(_start!)) {
      setState(() => _error = 'The end date must be after the start date.');
      return;
    }

    final categories = _categories.text.split(',').map((c) => c.trim()).where((c) => c.isNotEmpty).toList();
    final maxDiscount = double.tryParse(_maxDiscount.text.trim());
    final minOrder = double.tryParse(_minOrder.text.trim());
    final maxRedemptions = int.tryParse(_maxRedemptions.text.trim());

    final input = OfferInput(
      code: _code.text,
      name: _name.text,
      description: _description.text,
      offerType: _type,
      value: _type == 'free_shipping' ? 0 : (double.tryParse(_value.text.trim()) ?? 0),
      maxDiscount: maxDiscount,
      minOrderValue: minOrder,
      maxRedemptions: maxRedemptions,
      maxPerCustomer: int.tryParse(_maxPerCustomer.text.trim()) ?? 1,
      startsAt: _start,
      endsAt: _end,
      targetSegments: _segments.toList(),
      targetCategories: categories,
      priority: _priority.round(),
    );

    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final repository = ref.read(offersRepositoryProvider);
      if (_editing) {
        await repository.update(widget.offer!.id, input);
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

  Widget _dateButton({required bool start}) {
    final value = start ? _start : _end;
    final label = value == null
        ? (start ? 'Starts immediately' : 'No end date')
        : '${start ? 'Starts' : 'Ends'} ${DateFormat('d MMM y').format(value)}';
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: _saving ? null : () => _pickDate(start: start),
            icon: const Icon(Icons.event, size: 18),
            label: Text(label, overflow: TextOverflow.ellipsis),
          ),
        ),
        if (value != null)
          IconButton(
            tooltip: 'Clear',
            icon: const Icon(Icons.close, size: 18),
            onPressed: _saving ? null : () => setState(() => start ? _start = null : _end = null),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final segments = ref.watch(segmentOverviewProvider).valueOrNull?.segments ?? const [];

    return Dialog(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 660, maxHeight: 780),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(_editing ? 'Edit offer' : 'New offer', style: textTheme.headlineSmall)),
                  IconButton(
                    tooltip: 'Close',
                    icon: const Icon(Icons.close),
                    onPressed: _saving ? null : () => Navigator.of(context).pop(false),
                  ),
                ],
              ),
              if (!_editing)
                Text('New offers start as drafts. Activate them from the offer menu when ready.', style: textTheme.bodyMedium),
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
                                controller: _code,
                                enabled: !_editing && !_saving,
                                textCapitalization: TextCapitalization.characters,
                                decoration: const InputDecoration(labelText: 'Coupon code', hintText: 'WELCOME10', isDense: true),
                                validator: (v) => _codePattern.hasMatch((v ?? '').trim())
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
                          controller: _description,
                          enabled: !_saving,
                          minLines: 1,
                          maxLines: 3,
                          decoration: const InputDecoration(labelText: 'Description (optional)', isDense: true),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: InputDecorator(
                                decoration: const InputDecoration(
                                  labelText: 'Type',
                                  isDense: true,
                                  contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                ),
                                child: DropdownButtonHideUnderline(
                                  child: DropdownButton<String>(
                                    isExpanded: true,
                                    isDense: true,
                                    value: _type,
                                    items: [
                                      for (final type in kOfferTypes)
                                        DropdownMenuItem(value: type, child: Text(offerTypeLabel(type))),
                                    ],
                                    onChanged: _saving ? null : (value) => setState(() => _type = value ?? _type),
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: _type == 'free_shipping'
                                  ? const SizedBox.shrink()
                                  : TextFormField(
                                      controller: _value,
                                      enabled: !_saving,
                                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                      decoration: InputDecoration(
                                        labelText: _type == 'percent_off' ? 'Percent off' : 'Amount off',
                                        isDense: true,
                                      ),
                                      validator: (v) => _type == 'percent_off'
                                          ? _requiredNumber(v, min: 0.01, max: 100, label: 'Percent')
                                          : _requiredNumber(v, min: 0.01, label: 'Amount'),
                                    ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        Text('Guardrails', style: textTheme.titleMedium),
                        const SizedBox(height: 8),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: TextFormField(
                                controller: _maxDiscount,
                                enabled: !_saving,
                                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                decoration: const InputDecoration(labelText: 'Max discount', hintText: 'No cap', isDense: true),
                                validator: (v) => _optionalNumber(v, min: 0.01),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: TextFormField(
                                controller: _minOrder,
                                enabled: !_saving,
                                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                decoration: const InputDecoration(labelText: 'Min order value', hintText: 'None', isDense: true),
                                validator: (v) => _optionalNumber(v),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: TextFormField(
                                controller: _maxRedemptions,
                                enabled: !_saving,
                                keyboardType: TextInputType.number,
                                decoration: const InputDecoration(labelText: 'Total budget (uses)', hintText: 'Unlimited', isDense: true),
                                validator: (v) => _optionalNumber(v, min: 1),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: TextFormField(
                                controller: _maxPerCustomer,
                                enabled: !_saving,
                                keyboardType: TextInputType.number,
                                decoration: const InputDecoration(labelText: 'Uses per customer', isDense: true),
                                validator: (v) => _requiredNumber(v, min: 1, label: 'Uses per customer'),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        Text('Schedule', style: textTheme.titleMedium),
                        const SizedBox(height: 8),
                        _dateButton(start: true),
                        const SizedBox(height: 8),
                        _dateButton(start: false),
                        const SizedBox(height: 16),
                        Text('Who can get it', style: textTheme.titleMedium),
                        const SizedBox(height: 4),
                        Text(
                          _segments.isEmpty ? 'Everyone (no segment selected)' : 'Only the selected customer segments',
                          style: textTheme.bodyMedium,
                        ),
                        const SizedBox(height: 8),
                        if (segments.isEmpty)
                          Text('Segments appear here once customer profiles are computed.', style: textTheme.bodyMedium)
                        else
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              for (final segment in segments)
                                FilterChip(
                                  label: Text(segment.name),
                                  selected: _segments.contains(segment.key),
                                  onSelected: _saving
                                      ? null
                                      : (selected) => setState(() {
                                            if (selected) {
                                              _segments.add(segment.key);
                                            } else {
                                              _segments.remove(segment.key);
                                            }
                                          }),
                                ),
                            ],
                          ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _categories,
                          enabled: !_saving,
                          decoration: const InputDecoration(
                            labelText: 'Only for categories (comma separated, optional)',
                            hintText: 'Laptops, Smartphones',
                            isDense: true,
                          ),
                        ),
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Text('Priority', style: textTheme.titleMedium),
                            const SizedBox(width: 8),
                            Text('${_priority.round()}', style: textTheme.titleMedium?.copyWith(color: AppColors.primary)),
                          ],
                        ),
                        Slider(
                          value: _priority,
                          min: 0,
                          max: 100,
                          divisions: 20,
                          label: _priority.round().toString(),
                          onChanged: _saving ? null : (value) => setState(() => _priority = value),
                        ),
                        Text('Higher priority offers are shown first when several apply.', style: textTheme.bodyMedium),
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
                        : Text(_editing ? 'Save changes' : 'Create offer'),
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
