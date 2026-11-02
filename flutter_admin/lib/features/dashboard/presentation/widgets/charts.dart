import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../domain/overview.dart';

/// Simple vertical bar chart (one bar per day) built from plain widgets.
class DailyBars extends StatelessWidget {
  const DailyBars({super.key, required this.data, this.barAreaHeight = 150});

  final List<DayCount> data;
  final double barAreaHeight;

  @override
  Widget build(BuildContext context) {
    final maxValue = data.fold<int>(0, (max, d) => d.count > max ? d.count : max);
    final labelStyle = Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 10);

    return SizedBox(
      height: barAreaHeight + 30,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (final day in data)
            Expanded(
              child: Tooltip(
                message: '${day.date}: ${formatCount(day.count)} events',
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    Container(
                      height: maxValue == 0 ? 2.0 : (barAreaHeight * day.count / maxValue).clamp(2.0, barAreaHeight).toDouble(),
                      margin: const EdgeInsets.symmetric(horizontal: 3),
                      decoration: BoxDecoration(
                        color: AppColors.primary,
                        borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(day.date.length >= 10 ? day.date.substring(8) : day.date, style: labelStyle),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Horizontal ranked bars: label + count, with a proportional bar underneath.
class RankedBars extends StatelessWidget {
  const RankedBars({super.key, required this.items, this.color = AppColors.primary, this.labelBuilder});

  final List<NamedCount> items;
  final Color color;
  final String Function(String name)? labelBuilder;

  @override
  Widget build(BuildContext context) {
    final maxValue = items.fold<int>(0, (max, item) => item.count > max ? item.count : max);
    final textTheme = Theme.of(context).textTheme;

    return Column(
      children: [
        for (final item in items)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        labelBuilder == null ? item.name : labelBuilder!(item.name),
                        style: textTheme.bodyMedium,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text(formatCount(item.count), style: textTheme.bodyMedium),
                  ],
                ),
                const SizedBox(height: 4),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: maxValue == 0 ? 0.0 : item.count / maxValue,
                    minHeight: 6,
                    backgroundColor: color.withValues(alpha: 0.12),
                    valueColor: AlwaysStoppedAnimation<Color>(color),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
