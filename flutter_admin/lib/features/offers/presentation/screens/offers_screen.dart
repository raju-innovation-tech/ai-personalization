import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/adaptive_grid.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../../auth/domain/admin_user.dart';
import '../../../auth/presentation/providers/auth_controller.dart';
import '../../../auth/presentation/providers/auth_state.dart';
import '../../../dashboard/presentation/providers/dashboard_providers.dart';
import '../../domain/offer.dart';
import '../providers/offers_providers.dart';
import '../widgets/offer_form_dialog.dart';
import '../widgets/offer_suggestion_tile.dart';

Color offerStatusColor(String status) {
  switch (status) {
    case 'active':
      return AppColors.success;
    case 'scheduled':
      return AppColors.info;
    case 'paused':
      return AppColors.warning;
    case 'expired':
    case 'ended':
      return AppColors.danger;
    default: // draft
      return const Color(0xFF9CA3AF);
  }
}

class OffersScreen extends ConsumerStatefulWidget {
  const OffersScreen({super.key});

  @override
  ConsumerState<OffersScreen> createState() => _OffersScreenState();
}

class _OffersScreenState extends ConsumerState<OffersScreen> {
  final TextEditingController _search = TextEditingController();
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _search.text = ref.read(offerQueryProvider).search;
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _update(OfferQuery Function(OfferQuery current) change) {
    ref.read(offerQueryProvider.notifier).state = change(ref.read(offerQueryProvider));
  }

  void _onSearchChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 400), () {
      if (!mounted) return;
      _update((q) => q.copyWith(search: value));
    });
  }

  Future<void> _createOffer() async {
    final saved = await showDialog<bool>(context: context, builder: (_) => const OfferFormDialog());
    if (saved == true && mounted) refreshOffers(ref);
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final query = ref.watch(offerQueryProvider);
    final pageAsync = ref.watch(offersPageProvider);
    final totalsAsync = ref.watch(offerTotalsProvider);

    const statuses = <(String?, String)>[
      (null, 'All'),
      ('active', 'Active'),
      ('draft', 'Draft'),
      ('paused', 'Paused'),
      ('ended', 'Ended'),
      ('expired', 'Expired'),
    ];

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
                    Text('Offers', style: textTheme.headlineSmall),
                    const SizedBox(height: 4),
                    Text(
                      'Discount campaigns targeted at customer segments, with budgets and guardrails.',
                      style: textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              FilledButton.icon(
                onPressed: _createOffer,
                icon: const Icon(Icons.add, size: 20),
                label: const Text('New offer'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          totalsAsync.maybeWhen(
            data: (totals) => _TotalsStrip(totals: totals),
            orElse: () => const SizedBox.shrink(),
          ),
          const _Playground(),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              for (final entry in statuses)
                ChoiceChip(
                  label: Text(entry.$2),
                  selected: query.status == entry.$1,
                  onSelected: (_) => _update(
                    (q) => entry.$1 == null ? q.copyWith(clearStatus: true) : q.copyWith(status: entry.$1),
                  ),
                ),
              SizedBox(
                width: 240,
                child: TextField(
                  controller: _search,
                  onChanged: _onSearchChanged,
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.search),
                    hintText: 'Search name or code',
                    isDense: true,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          pageAsync.when(
            loading: () => const Padding(padding: EdgeInsets.all(32), child: LoadingState(message: 'Loading offers...')),
            error: (error, _) => ErrorState(
              message: errorMessageOf(error),
              onRetry: () => ref.invalidate(offersPageProvider),
            ),
            data: (page) {
              if (page.items.isEmpty) {
                return const EmptyState(
                  title: 'No offers found',
                  subtitle: 'Create your first offer with the New offer button, or change the filter.',
                  icon: Icons.local_offer_outlined,
                );
              }
              return Column(
                children: [
                  for (final offer in page.items) ...[
                    _OfferCard(offer: offer),
                    const SizedBox(height: 12),
                  ],
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          '${formatCount(page.total)} offers  •  page ${page.page} of ${page.totalPages}',
                          style: textTheme.bodyMedium,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      IconButton(
                        tooltip: 'Previous page',
                        icon: const Icon(Icons.chevron_left),
                        onPressed: page.page > 1 ? () => _update((q) => q.copyWith(page: page.page - 1)) : null,
                      ),
                      IconButton(
                        tooltip: 'Next page',
                        icon: const Icon(Icons.chevron_right),
                        onPressed: page.page < page.totalPages ? () => _update((q) => q.copyWith(page: page.page + 1)) : null,
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

/// Reload everything that shows offer numbers.
void refreshOffers(WidgetRef ref) {
  ref.invalidate(offersPageProvider);
  ref.invalidate(offerTotalsProvider);
  ref.invalidate(dashboardOverviewProvider);
}

class _TotalsStrip extends StatelessWidget {
  const _TotalsStrip({required this.totals});

  final OfferTotals totals;

  @override
  Widget build(BuildContext context) {
    final tiles = <(String, String)>[
      ('Active now', formatCount(totals.activeNow)),
      ('Impressions', formatCount(totals.impressions)),
      ('Clicks (CTR ${formatPercent(totals.ctr)})', formatCount(totals.clicks)),
      ('Redemptions', formatCount(totals.redemptions)),
      ('Redemption rate', formatPercent(totals.redemptionRate)),
      ('Discount given', formatCompactPrice(totals.discountGiven)),
      ('Revenue with offers', formatCompactPrice(totals.revenue)),
    ];
    final textTheme = Theme.of(context).textTheme;

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: AdaptiveGrid(
        itemMinWidth: 140,
        children: [
          for (final tile in tiles)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.primary.withValues(alpha: 0.06),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(tile.$2, style: textTheme.titleMedium),
                  const SizedBox(height: 2),
                  Text(tile.$1, style: textTheme.bodyMedium?.copyWith(fontSize: 12), maxLines: 2, overflow: TextOverflow.ellipsis),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _OfferCard extends ConsumerWidget {
  const _OfferCard({required this.offer});

  final Offer offer;

  List<PopupMenuEntry<String>> _menuItems(bool canDelete) {
    final items = <PopupMenuEntry<String>>[];
    if (offer.status != 'ended') {
      items.add(const PopupMenuItem(value: 'edit', child: Text('Edit')));
    }
    if (offer.status == 'draft' || offer.status == 'paused') {
      items.add(PopupMenuItem(value: 'activate', child: Text(offer.status == 'paused' ? 'Resume' : 'Activate')));
    }
    if (offer.status == 'active') {
      items.add(const PopupMenuItem(value: 'pause', child: Text('Pause')));
    }
    if (offer.status != 'ended') {
      items.add(const PopupMenuItem(value: 'end', child: Text('End offer')));
    }
    if (canDelete) {
      items.add(
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
      );
    }
    return items;
  }

  Future<void> _onMenu(BuildContext context, WidgetRef ref, String action) async {
    final messenger = ScaffoldMessenger.of(context);

    if (action == 'edit') {
      final saved = await showDialog<bool>(context: context, builder: (_) => OfferFormDialog(offer: offer));
      if (saved == true && context.mounted) refreshOffers(ref);
      return;
    }

    if (action == 'delete') {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Delete this offer?'),
          content: Text('Are you sure you want to delete "${offer.name}" (${offer.code})? This action cannot be undone.'),
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
        await ref.read(offersRepositoryProvider).deleteOffer(offer.id);
        if (context.mounted) refreshOffers(ref);
        messenger.showSnackBar(
          SnackBar(
            content: Text('Offer "${offer.name}" (${offer.code}) deleted successfully.'),
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
      return;
    }

    if (action == 'end') {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('End this offer?'),
          content: Text('${offer.name} (${offer.code}) will stop being served and cannot be restarted.'),
          actions: [
            TextButton(onPressed: () => Navigator.of(dialogContext).pop(false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.of(dialogContext).pop(true), child: const Text('End offer')),
          ],
        ),
      );
      if (confirmed != true || !context.mounted) return;
    }

    const targets = {'activate': 'active', 'pause': 'paused', 'end': 'ended'};
    final status = targets[action];
    if (status == null) return;
    try {
      await ref.read(offersRepositoryProvider).setStatus(offer.id, status);
      if (context.mounted) refreshOffers(ref);
      messenger.showSnackBar(SnackBar(content: Text('${offer.code} is now $status.')));
    } catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(errorMessageOf(error))));
    }
  }

  String _schedule() {
    final format = DateFormat('d MMM y');
    final start = offer.startsAt == null ? null : DateTime.tryParse(offer.startsAt!)?.toLocal();
    final end = offer.endsAt == null ? null : DateTime.tryParse(offer.endsAt!)?.toLocal();
    if (start == null && end == null) return 'Always on';
    if (end == null) return 'From ${format.format(start!)}';
    if (start == null) return 'Until ${format.format(end)}';
    return '${format.format(start)} → ${format.format(end)}';
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final small = textTheme.bodyMedium?.copyWith(fontSize: 12);
    final stats = offer.stats;
    final statusColor = offerStatusColor(offer.effectiveStatus);
    final auth = ref.watch(authControllerProvider);
    final user = auth is AuthAuthenticated ? auth.user : null;
    final isSuperAdmin = user?.role == UserRole.superAdmin;
    final isAdmin = user?.role == UserRole.admin;
    final canDelete = isSuperAdmin || (isAdmin && offer.status == 'draft');
    final menu = _menuItems(canDelete);

    final rules = [
      offer.headline,
      if (offer.minOrderValue != null) 'min order ${formatPrice(offer.minOrderValue)}',
      '${offer.maxPerCustomer} per customer',
      if (offer.maxRedemptions != null) 'budget ${formatCount(offer.maxRedemptions!)}',
    ].join('  •  ');

    final audience = <String>[
      if (offer.targetSegments.isEmpty) 'Everyone' else offer.targetSegments.map(humanize).join(', '),
      if (offer.targetCategories.isNotEmpty) 'in ${offer.targetCategories.join(', ')}',
    ].join(' ');

    final numbers = <(String, String)>[
      ('Impressions', formatCount(stats.impressions)),
      ('Clicks', '${formatCount(stats.clicks)} (${formatPercent(stats.ctr)})'),
      (
        'Redeemed',
        stats.remaining == null
            ? formatCount(stats.redemptions)
            : '${formatCount(stats.redemptions)} / ${formatCount(offer.maxRedemptions ?? 0)}',
      ),
      ('Discount given', formatCompactPrice(stats.discountGiven)),
      ('Revenue', formatCompactPrice(stats.revenue)),
    ];

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
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
                      Text(offer.name, style: textTheme.titleMedium),
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 8,
                        runSpacing: 6,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          CodeChip(offer.code),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
                            decoration: BoxDecoration(
                              color: statusColor.withValues(alpha: 0.13),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Text(
                              humanize(offer.effectiveStatus),
                              style: TextStyle(color: statusColor, fontSize: 11.5, fontWeight: FontWeight.w700),
                            ),
                          ),
                          Text(offerTypeLabel(offer.offerType), style: small),
                        ],
                      ),
                    ],
                  ),
                ),
                if (menu.isNotEmpty)
                  PopupMenuButton<String>(
                    tooltip: 'Actions',
                    onSelected: (action) => _onMenu(context, ref, action),
                    itemBuilder: (_) => menu,
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Text(rules, style: textTheme.titleMedium?.copyWith(fontSize: 14)),
            const SizedBox(height: 4),
            if (offer.description != null && offer.description!.isNotEmpty) ...[
              Text(offer.description!, style: textTheme.bodyMedium),
              const SizedBox(height: 4),
            ],
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.groups_outlined, size: 15),
                const SizedBox(width: 6),
                Expanded(child: Text(audience, style: small)),
              ],
            ),
            const SizedBox(height: 2),
            Row(
              children: [
                const Icon(Icons.event_outlined, size: 15),
                const SizedBox(width: 6),
                Expanded(child: Text('${_schedule()}  •  priority ${offer.priority}', style: small)),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 20,
              runSpacing: 8,
              children: [
                for (final entry in numbers)
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(entry.$2, style: textTheme.titleMedium?.copyWith(fontSize: 14)),
                      Text(entry.$1, style: small),
                    ],
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// "Try it": the offers the engine would show a customer right now.
class _Playground extends ConsumerStatefulWidget {
  const _Playground();

  @override
  ConsumerState<_Playground> createState() => _PlaygroundState();
}

class _PlaygroundState extends ConsumerState<_Playground> {
  final TextEditingController _user = TextEditingController(text: '1882');
  final TextEditingController _category = TextEditingController();
  final TextEditingController _cart = TextEditingController();
  Future<List<OfferSuggestion>>? _future;

  @override
  void dispose() {
    _user.dispose();
    _category.dispose();
    _cart.dispose();
    super.dispose();
  }

  void _run() {
    final user = _user.text.trim();
    if (user.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Enter a customer ID first.')));
      return;
    }
    final future = ref.read(offersRepositoryProvider).forUser(
          user,
          category: _category.text,
          cartValue: double.tryParse(_cart.text.trim()),
        );
    setState(() {
      _future = future;
    });
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Card(
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 18),
          childrenPadding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          title: Text('Try it: offers for a customer', style: textTheme.titleMedium),
          subtitle: Text('Run the storefront API and see why each offer is shown.', style: textTheme.bodyMedium),
          children: [
            LayoutBuilder(
              builder: (context, constraints) {
                final isSmall = constraints.maxWidth < 600;
                final fieldWidth = isSmall ? constraints.maxWidth : null;
                return Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    SizedBox(
                      width: isSmall ? fieldWidth : 200,
                      child: TextField(
                        controller: _user,
                        onSubmitted: (_) => _run(),
                        decoration: const InputDecoration(labelText: 'Customer ID', isDense: true),
                      ),
                    ),
                    SizedBox(
                      width: isSmall ? fieldWidth : 180,
                      child: TextField(
                        controller: _category,
                        decoration: const InputDecoration(labelText: 'Browsing category', hintText: 'optional', isDense: true),
                      ),
                    ),
                    SizedBox(
                      width: isSmall ? fieldWidth : 150,
                      child: TextField(
                        controller: _cart,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(labelText: 'Cart value', hintText: 'optional', isDense: true),
                      ),
                    ),
                    SizedBox(
                      width: isSmall ? fieldWidth : null,
                      child: FilledButton.icon(
                        onPressed: _run,
                        icon: const Icon(Icons.play_arrow_rounded, size: 20),
                        label: const Text('Get offers'),
                      ),
                    ),
                  ],
                );
              },
            ),
            const SizedBox(height: 12),
            if (_future == null)
              Text('Enter a customer and press the button.', style: textTheme.bodyMedium)
            else
              FutureBuilder<List<OfferSuggestion>>(
                future: _future,
                builder: (context, snapshot) {
                  if (snapshot.connectionState != ConnectionState.done) {
                    return const Padding(
                      padding: EdgeInsets.all(12),
                      child: Center(child: CircularProgressIndicator(strokeWidth: 2.5)),
                    );
                  }
                  if (snapshot.hasError) {
                    return Text(errorMessageOf(snapshot.error!), style: textTheme.bodyMedium);
                  }
                  final offers = snapshot.data ?? const <OfferSuggestion>[];
                  if (offers.isEmpty) {
                    return Text('No offers are available for this customer right now.', style: textTheme.bodyMedium);
                  }
                  return Column(
                    children: [
                      for (var i = 0; i < offers.length; i++) ...[
                        if (i > 0) const Divider(height: 1),
                        OfferSuggestionTile(offer: offers[i]),
                      ],
                    ],
                  );
                },
              ),
          ],
        ),
      ),
    );
  }
}
