import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../customers/presentation/providers/customers_providers.dart';
import '../providers/segments_providers.dart';

/// Asks the server to recompute customer profiles, RFM scores and segments,
/// then refreshes every screen that shows them (admin only on the server).
class RecomputeButton extends ConsumerStatefulWidget {
  const RecomputeButton({super.key});

  @override
  ConsumerState<RecomputeButton> createState() => _RecomputeButtonState();
}

class _RecomputeButtonState extends ConsumerState<RecomputeButton> {
  bool _busy = false;

  Future<void> _run() async {
    setState(() => _busy = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(customersRepositoryProvider).recompute();
      ref.invalidate(segmentOverviewProvider);
      ref.invalidate(customerOverviewProvider);
      ref.invalidate(customersPageProvider);
      messenger.showSnackBar(const SnackBar(content: Text('Customer segments recomputed.')));
    } catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(errorMessageOf(error))));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: _busy ? null : _run,
      icon: _busy
          ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
          : const Icon(Icons.refresh, size: 18),
      label: const Text('Recompute'),
    );
  }
}
