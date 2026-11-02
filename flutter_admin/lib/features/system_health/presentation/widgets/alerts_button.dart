import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/theme/app_colors.dart';
import '../../domain/system.dart';
import '../providers/system_providers.dart';

Color alertColor(String severity) {
  switch (severity) {
    case 'critical':
      return AppColors.danger;
    case 'warning':
      return AppColors.warning;
    default:
      return AppColors.info;
  }
}

IconData alertIcon(String severity) {
  switch (severity) {
    case 'critical':
      return Icons.error_outline;
    case 'warning':
      return Icons.warning_amber_rounded;
    default:
      return Icons.info_outline;
  }
}

/// One alert: coloured icon, title and message.
class AlertTile extends StatelessWidget {
  const AlertTile({super.key, required this.alert});

  final AppAlert alert;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final color = alertColor(alert.severity);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(alertIcon(alert.severity), size: 20, color: color),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(alert.title, style: textTheme.titleMedium?.copyWith(fontSize: 14)),
              const SizedBox(height: 2),
              Text(alert.message, style: textTheme.bodyMedium?.copyWith(fontSize: 12.5)),
            ],
          ),
        ),
      ],
    );
  }
}

/// The notification bell: a badge with the number of things that need attention, and a list of alerts.
class AlertsButton extends ConsumerWidget {
  const AlertsButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final alerts = ref.watch(systemAlertsProvider).valueOrNull;
    final attention = alerts?.needsAttention ?? 0;

    return PopupMenuButton<String>(
      tooltip: 'Notifications',
      offset: const Offset(0, 44),
      onOpened: () => ref.invalidate(systemAlertsProvider),
      onSelected: (link) {
        if (link.isNotEmpty) context.go(link);
      },
      icon: Badge(
        isLabelVisible: attention > 0,
        label: Text('$attention'),
        child: const Icon(Icons.notifications_outlined),
      ),
      itemBuilder: (context) {
        final items = alerts?.items ?? const <AppAlert>[];
        if (items.isEmpty) {
          return [
            const PopupMenuItem<String>(
              enabled: false,
              child: Text('All clear - nothing needs your attention.'),
            ),
          ];
        }
        return [
          for (final alert in items)
            PopupMenuItem<String>(
              value: alert.link ?? '',
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 340),
                child: AlertTile(alert: alert),
              ),
            ),
        ];
      },
    );
  }
}
