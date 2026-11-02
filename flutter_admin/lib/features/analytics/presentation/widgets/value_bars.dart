import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';

/// Vertical bar chart for any series of numbers (one bar per day), built from plain widgets.
class ValueBars extends StatelessWidget {
  const ValueBars({
    super.key,
    required this.values,
    required this.dates,
    required this.format,
    this.color = AppColors.primary,
    this.barAreaHeight = 170,
  });

  final List<double> values;
  final List<String> dates; // yyyy-MM-dd, same length as values
  final String Function(double value) format;
  final Color color;
  final double barAreaHeight;

  @override
  Widget build(BuildContext context) {
    final maxValue = values.fold<double>(0, (max, v) => v > max ? v : max);
    final labelStyle = Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 10);
    final step = (values.length / 10).ceil().clamp(1, 1000).toInt(); // show roughly 10 labels
    final gap = values.length > 45 ? 0.5 : 2.0;

    return SizedBox(
      height: barAreaHeight + 30,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (var i = 0; i < values.length; i++)
            Expanded(
              child: Tooltip(
                message: '${dates[i]}: ${format(values[i])}',
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    Container(
                      height: maxValue <= 0 ? 2.0 : (barAreaHeight * values[i] / maxValue).clamp(2.0, barAreaHeight).toDouble(),
                      margin: EdgeInsets.symmetric(horizontal: gap),
                      decoration: BoxDecoration(
                        color: color,
                        borderRadius: const BorderRadius.vertical(top: Radius.circular(3)),
                      ),
                    ),
                    const SizedBox(height: 6),
                    SizedBox(
                      height: 14,
                      child: i % step == 0
                          ? FittedBox(
                              fit: BoxFit.scaleDown,
                              child: Text(dates[i].length >= 10 ? dates[i].substring(5) : dates[i], style: labelStyle),
                            )
                          : null,
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
