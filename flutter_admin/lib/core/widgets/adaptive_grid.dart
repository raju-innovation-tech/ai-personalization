import 'package:flutter/material.dart';

/// Renders a list of widgets in an adaptive, fully responsive grid
/// that automatically computes each item's width so cards always fill
/// 100% of the available horizontal width with zero empty right-side gaps.
class AdaptiveGrid extends StatelessWidget {
  const AdaptiveGrid({
    super.key,
    required this.children,
    this.spacing = 12.0,
    this.runSpacing = 12.0,
    this.itemMinWidth = 150.0,
    this.maxColumns,
    this.mobileColumns = 2,
  });

  final List<Widget> children;
  final double spacing;
  final double runSpacing;
  final double itemMinWidth;
  final int? maxColumns;
  final int mobileColumns;

  @override
  Widget build(BuildContext context) {
    if (children.isEmpty) return const SizedBox.shrink();

    return LayoutBuilder(
      builder: (context, constraints) {
        final availableWidth = constraints.maxWidth;
        if (availableWidth <= 0) return const SizedBox.shrink();

        int columns;
        if (availableWidth < 340) {
          columns = 1;
        } else if (availableWidth < 600) {
          columns = mobileColumns;
        } else {
          columns = ((availableWidth + spacing) / (itemMinWidth + spacing)).floor();
        }

        if (maxColumns != null && columns > maxColumns!) {
          columns = maxColumns!;
        }
        if (columns < 1) columns = 1;

        // Ensure itemWidth exactly spans availableWidth with zero leftover gap
        final itemWidth = (availableWidth - (columns - 1) * spacing) / columns;

        return Wrap(
          spacing: spacing,
          runSpacing: runSpacing,
          children: children.map((child) => SizedBox(width: itemWidth, child: child)).toList(),
        );
      },
    );
  }
}
