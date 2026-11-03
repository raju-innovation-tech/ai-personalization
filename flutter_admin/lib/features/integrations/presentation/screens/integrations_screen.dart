import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_constants.dart';
import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/adaptive_grid.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../domain/integration_status.dart';
import '../providers/integrations_providers.dart';

/// Copy-paste examples; {BASE} is replaced with the API address this app is using.
const List<(String, String)> _snippets = [
  (
    '1. Get a token (service account)',
    r'''curl -X POST {BASE}/auth/login -H "Content-Type: application/json" \
  -d '{"email":"shop@yourstore.com","password":"YOUR_PASSWORD"}' ''',
  ),
  (
    '2. Push your product catalog (token needed)',
    r'''curl -X POST {BASE}/products/bulk -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" \
  -d '{"products":[{"product_id":"SKU-1","name":"Acme Laptop","category":"Laptops","brand":"Acme","price":59999,"in_stock":true}]}' ''',
  ),
  (
    '3. Send customer events (no token)',
    r'''curl -X POST {BASE}/events -H "Content-Type: application/json" \
  -d '{"event_type":"PURCHASE","external_user_id":"1882","product_id":"2608911","session_id":"order-77","metadata":{"quantity":1}}' ''',
  ),
  (
    '4. Show recommendations (no token)',
    r'''curl "{BASE}/recommendations/user/1882?limit=8"
curl "{BASE}/recommendations/similar/2608911"''',
  ),
  (
    '5. Show offers for a customer (no token)',
    r'''curl "{BASE}/offers/user/1882?cart_value=2500"''',
  ),
  (
    '6. Checkout: validate, then redeem (token needed)',
    r'''curl -X POST {BASE}/offers/validate -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" \
  -d '{"code":"WELFOG","external_user_id":"1882","order_value":2500}'
curl -X POST {BASE}/offers/redeem -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" \
  -d '{"code":"WELFOG","external_user_id":"1882","order_id":"ORD-1001","order_value":2500}' ''',
  ),
];

class IntegrationsScreen extends ConsumerWidget {
  const IntegrationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final statusAsync = ref.watch(integrationStatusProvider);

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
                    Text('Integrations', style: textTheme.headlineSmall),
                    const SizedBox(height: 4),
                    Text('Connect your shop and check that the data it sends is healthy.', style: textTheme.bodyMedium),
                  ],
                ),
              ),
              IconButton(
                tooltip: 'Refresh',
                icon: const Icon(Icons.refresh),
                onPressed: () => ref.invalidate(integrationStatusProvider),
              ),
            ],
          ),
          const SizedBox(height: 16),
          statusAsync.when(
            loading: () => const Padding(padding: EdgeInsets.all(32), child: LoadingState(message: 'Checking integration...')),
            error: (error, _) => ErrorState(
              message: errorMessageOf(error),
              onRetry: () => ref.invalidate(integrationStatusProvider),
            ),
            data: (status) => _Body(status: status),
          ),
          const SizedBox(height: 16),
          const _SnippetsCard(),
        ],
      ),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.status});

  final IntegrationStatus status;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final small = textTheme.bodyMedium?.copyWith(fontSize: 12);

    final progress = Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Setup progress', style: textTheme.titleMedium),
            const SizedBox(height: 4),
            Text('${status.doneCount} of ${status.checklist.length} steps done', style: textTheme.bodyMedium),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(
                value: status.score.clamp(0.0, 1.0).toDouble(),
                minHeight: 10,
                backgroundColor: AppColors.primary.withValues(alpha: 0.12),
                valueColor: const AlwaysStoppedAnimation<Color>(AppColors.success),
              ),
            ),
            const SizedBox(height: 14),
            for (final item in status.checklist) _ChecklistRow(item: item),
          ],
        ),
      ),
    );

    final tiles = <(String, String, String?)>[
      ('Events (24h)', formatCount(status.events24h), 'last: ${status.lastEventAt == null ? 'never' : formatTimestamp(status.lastEventAt!)}'),
      ('Events (7 days)', formatCount(status.events7d), '${formatCount(status.eventsTotal)} in total'),
      ('Products', formatCount(status.products), '${formatCount(status.activeProducts)} active, ${formatCount(status.outOfStock)} out of stock'),
      (
        'Unknown product ids',
        formatPercent(status.unknownProductRate),
        '${formatCount(status.unknownProductEvents30d)} of ${formatCount(status.productEvents30d)} events (30d)',
      ),
      (
        'Purchases without session',
        formatPercent(status.purchasesWithoutSessionRate),
        '${formatCount(status.purchasesWithoutSession30d)} of ${formatCount(status.purchaseEvents30d)} (30d)',
      ),
      ('Recommendations served', formatCount(status.recommendationsServed), null),
      ('Offers redeemed', formatCount(status.redemptions), null),
    ];

    final health = Card(
      child: SizedBox(
        width: double.infinity,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Data health', style: textTheme.titleMedium),
              const SizedBox(height: 12),
              AdaptiveGrid(
                itemMinWidth: 160,
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
                          Text(tile.$1, style: small),
                          if (tile.$3 != null) Text(tile.$3!, style: small?.copyWith(fontSize: 11)),
                        ],
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );

    final accounts = status.accounts;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        progress,
        const SizedBox(height: 16),
        health,
        if (accounts != null) ...[
          const SizedBox(height: 16),
          Card(
            child: SizedBox(
              width: double.infinity,
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Accounts that can sign in', style: textTheme.titleMedium),
                    const SizedBox(height: 4),
                    Text('Manage them on the Users page. Use a dedicated account for your shop.', style: textTheme.bodyMedium),
                    const SizedBox(height: 10),
                    for (final account in accounts)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 4),
                        child: Row(
                          children: [
                            Icon(
                              account.isActive ? Icons.check_circle_outline : Icons.block,
                              size: 16,
                              color: account.isActive ? AppColors.success : AppColors.danger,
                            ),
                            const SizedBox(width: 8),
                            Expanded(child: Text(account.email, overflow: TextOverflow.ellipsis)),
                            Text(humanize(account.role), style: small),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _ChecklistRow extends StatelessWidget {
  const _ChecklistRow({required this.item});

  final ChecklistItem item;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    late final IconData icon;
    late final Color color;
    switch (item.status) {
      case 'ok':
        icon = Icons.check_circle;
        color = AppColors.success;
      case 'warning':
        icon = Icons.warning_amber_rounded;
        color = AppColors.warning;
      default:
        icon = Icons.radio_button_unchecked;
        color = const Color(0xFF9CA3AF);
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.title, style: textTheme.titleMedium?.copyWith(fontSize: 14)),
                Text(item.detail, style: textTheme.bodyMedium?.copyWith(fontSize: 12.5)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SnippetsCard extends StatelessWidget {
  const _SnippetsCard();

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Card(
      child: SizedBox(
        width: double.infinity,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Connect your shop', style: textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(
                'API address: ${AppConstants.apiBaseUrl}   (interactive docs: the same server, path /docs). '
                'Examples use curl; PowerShell versions are in the README.',
                style: textTheme.bodyMedium,
              ),
              const SizedBox(height: 14),
              for (final snippet in _snippets) ...[
                Text(snippet.$1, style: textTheme.titleMedium?.copyWith(fontSize: 13.5)),
                const SizedBox(height: 6),
                _CodeBlock(code: snippet.$2.replaceAll('{BASE}', AppConstants.apiBaseUrl).trimRight(), dark: isDark),
                const SizedBox(height: 14),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _CodeBlock extends StatelessWidget {
  const _CodeBlock({required this.code, required this.dark});

  final String code;
  final bool dark;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 8, 4, 8),
      decoration: BoxDecoration(
        color: dark ? const Color(0xFF0B1220) : const Color(0xFFF3F4F6),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: SelectableText(code, style: const TextStyle(fontFamily: 'monospace', fontSize: 12, height: 1.4)),
            ),
          ),
          IconButton(
            tooltip: 'Copy',
            icon: const Icon(Icons.copy, size: 18),
            onPressed: () async {
              final messenger = ScaffoldMessenger.of(context);
              await Clipboard.setData(ClipboardData(text: code));
              messenger.showSnackBar(const SnackBar(content: Text('Copied to clipboard')));
            },
          ),
        ],
      ),
    );
  }
}
