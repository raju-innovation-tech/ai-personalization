import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/state_widgets.dart';
import '../../../dashboard/domain/overview.dart';
import '../../../dashboard/presentation/widgets/charts.dart';
import '../../domain/system.dart';
import '../providers/system_providers.dart';
import '../widgets/alerts_button.dart';

class SystemScreen extends ConsumerWidget {
  const SystemScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final statusAsync = ref.watch(systemStatusProvider);
    final alertsAsync = ref.watch(systemAlertsProvider);

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
                    Text('System', style: textTheme.headlineSmall),
                    const SizedBox(height: 4),
                    Text('Health of the API, database, cache and background jobs.', style: textTheme.bodyMedium),
                  ],
                ),
              ),
              IconButton(
                tooltip: 'Refresh',
                icon: const Icon(Icons.refresh),
                onPressed: () {
                  ref.invalidate(systemStatusProvider);
                  ref.invalidate(systemAlertsProvider);
                },
              ),
            ],
          ),
          const SizedBox(height: 16),
          _AlertsCard(alertsAsync: alertsAsync),
          const SizedBox(height: 16),
          statusAsync.when(
            loading: () => const Padding(padding: EdgeInsets.all(32), child: LoadingState(message: 'Checking system...')),
            error: (error, _) => ErrorState(
              message: errorMessageOf(error),
              onRetry: () => ref.invalidate(systemStatusProvider),
            ),
            data: (status) => _StatusBody(status: status),
          ),
        ],
      ),
    );
  }
}

class _AlertsCard extends StatelessWidget {
  const _AlertsCard({required this.alertsAsync});

  final AsyncValue<AlertsResult> alertsAsync;

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
              Text('Alerts', style: textTheme.titleMedium),
              const SizedBox(height: 8),
              alertsAsync.when(
                loading: () => const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
                ),
                error: (error, _) => Text(errorMessageOf(error), style: textTheme.bodyMedium),
                data: (alerts) {
                  if (alerts.items.isEmpty) {
                    return Row(
                      children: [
                        const Icon(Icons.check_circle_outline, color: AppColors.success, size: 20),
                        const SizedBox(width: 8),
                        Text('All clear - nothing needs your attention.', style: textTheme.bodyMedium),
                      ],
                    );
                  }
                  return Column(
                    children: [
                      for (var i = 0; i < alerts.items.length; i++) ...[
                        if (i > 0) const Divider(height: 20),
                        AlertTile(alert: alerts.items[i]),
                      ],
                    ],
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusBody extends StatelessWidget {
  const _StatusBody({required this.status});

  final SystemStatus status;

  @override
  Widget build(BuildContext context) {
    final cards = <Widget>[
      _InfoCard(
        title: 'Application',
        icon: Icons.apps_outlined,
        ok: true,
        rows: [
          ('Name', status.appName),
          ('Version', status.version),
          ('Environment', status.environment),
          ('Uptime', formatDuration(status.uptimeSeconds)),
          ('Started', formatTimestamp(status.startedAt)),
        ],
      ),
      _InfoCard(
        title: 'Database (PostgreSQL)',
        icon: Icons.storage_outlined,
        ok: status.dbOk,
        rows: [
          ('Status', status.dbOk ? 'Connected' : 'Unavailable'),
          ('Latency', status.dbLatencyMs == null ? '—' : '${status.dbLatencyMs} ms'),
          ('Version', status.dbVersion ?? '—'),
          ('Size', formatBytes(status.dbSizeBytes)),
          ('Migration', status.migration ?? '—'),
        ],
      ),
      _InfoCard(
        title: 'Cache (Redis)',
        icon: Icons.memory_outlined,
        ok: status.redisOk,
        rows: [
          ('Status', status.redisOk ? 'Connected' : 'Unavailable'),
          ('Latency', status.redisLatencyMs == null ? '—' : '${status.redisLatencyMs} ms'),
          ('Version', status.redisVersion ?? '—'),
          ('Memory', formatBytes(status.redisMemoryBytes)),
          if (status.redisError != null) ('Error', status.redisError!),
        ],
      ),
      _InfoCard(
        title: 'Background jobs and models',
        icon: Icons.schedule_outlined,
        ok: true,
        rows: [
          (
            'Segment refresh',
            status.profileRefreshMinutes == 0 ? 'Manual only' : 'Every ${status.profileRefreshMinutes} min',
          ),
          ('Segments computed', status.profilesComputedAt == null ? 'Never' : formatTimestamp(status.profilesComputedAt!)),
          ('Recommendation model', status.snapshotBuiltAt == null ? 'Not built yet' : formatTimestamp(status.snapshotBuiltAt!)),
          ('Model cache', '${status.snapshotTtlSeconds} s'),
        ],
      ),
    ];

    final tables = [for (final t in status.tables) NamedCount(name: t.name, count: t.rows)]
      ..sort((a, b) => b.count.compareTo(a.count));
    final textTheme = Theme.of(context).textTheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        LayoutBuilder(
          builder: (context, constraints) {
            final columns = constraints.maxWidth >= 900 ? 2 : 1;
            final width = (constraints.maxWidth - 16 * (columns - 1)) / columns;
            return Wrap(
              spacing: 16,
              runSpacing: 16,
              children: [for (final card in cards) SizedBox(width: width, child: card)],
            );
          },
        ),
        const SizedBox(height: 16),
        Card(
          child: SizedBox(
            width: double.infinity,
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Database tables (rows)', style: textTheme.titleMedium),
                  const SizedBox(height: 14),
                  RankedBars(items: tables),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        Card(
          child: SizedBox(
            width: double.infinity,
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Active settings', style: textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text('Change these in backend/.env and restart the backend.', style: textTheme.bodyMedium),
                  const SizedBox(height: 12),
                  for (final entry in status.config.entries)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Row(
                        children: [
                          Expanded(child: Text(humanize(entry.key), style: textTheme.bodyMedium)),
                          Text('${entry.value}', style: textTheme.bodyLarge),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.title, required this.icon, required this.ok, required this.rows});

  final String title;
  final IconData icon;
  final bool ok;
  final List<(String, String)> rows;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final color = ok ? AppColors.success : AppColors.danger;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 20, color: color),
                const SizedBox(width: 8),
                Expanded(child: Text(title, style: textTheme.titleMedium)),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
                  decoration: BoxDecoration(color: color.withValues(alpha: 0.13), borderRadius: BorderRadius.circular(20)),
                  child: Text(
                    ok ? 'OK' : 'Problem',
                    style: TextStyle(color: color, fontSize: 11.5, fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            for (final row in rows)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(width: 130, child: Text(row.$1, style: textTheme.bodyMedium)),
                    Expanded(child: Text(row.$2, style: textTheme.bodyLarge)),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
