import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../domain/recommendation.dart';

Color algorithmColor(String algorithm) {
  switch (algorithm) {
    case 'popular':
      return AppColors.warning;
    case 'content':
      return AppColors.info;
    case 'collaborative':
      return AppColors.success;
    default: // fbt, hybrid, similar, ...
      return AppColors.primary;
  }
}

String algorithmLabel(String algorithm) {
  switch (algorithm) {
    case 'fbt':
      return 'Bought together';
    case 'collaborative':
      return 'Collaborative';
    default:
      return humanize(algorithm);
  }
}

class AlgorithmChip extends StatelessWidget {
  const AlgorithmChip(this.algorithm, {super.key});

  final String algorithm;

  @override
  Widget build(BuildContext context) {
    final color = algorithmColor(algorithm);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        algorithmLabel(algorithm),
        style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }
}

/// One recommended product with the reason the engine picked it.
class RecommendationTile extends StatelessWidget {
  const RecommendationTile({super.key, required this.item, this.rank});

  final RecommendationItem item;
  final int? rank;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final meta = [item.category, item.brand].whereType<String>().join(' • ');
    final small = textTheme.bodyMedium?.copyWith(fontSize: 12);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (rank != null) SizedBox(width: 28, child: Text('$rank', style: textTheme.titleMedium)),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.name,
                  style: textTheme.titleMedium?.copyWith(fontSize: 14),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  meta.isEmpty ? item.productId : '${item.productId} • $meta',
                  style: small,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Text(item.reason, style: textTheme.bodyMedium, maxLines: 2, overflow: TextOverflow.ellipsis),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(formatPrice(item.price), style: textTheme.titleMedium?.copyWith(fontSize: 14)),
              const SizedBox(height: 6),
              AlgorithmChip(item.algorithm),
              const SizedBox(height: 4),
              Text('score ${item.score.toStringAsFixed(2)}', style: small?.copyWith(fontSize: 11)),
            ],
          ),
        ],
      ),
    );
  }
}

/// Renders an async recommendation list (used inside the product detail dialog).
class RecommendationList extends StatelessWidget {
  const RecommendationList({super.key, required this.result, required this.emptyText});

  final AsyncValue<RecommendationResult> result;
  final String emptyText;

  @override
  Widget build(BuildContext context) {
    return result.when(
      loading: () => const Padding(
        padding: EdgeInsets.symmetric(vertical: 16),
        child: Center(child: SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5))),
      ),
      error: (error, _) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Text(errorMessageOf(error), style: Theme.of(context).textTheme.bodyMedium),
      ),
      data: (data) {
        if (data.items.isEmpty) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(emptyText, style: Theme.of(context).textTheme.bodyMedium),
          );
        }
        return Column(
          children: [
            for (var i = 0; i < data.items.length; i++) ...[
              if (i > 0) const Divider(height: 1),
              RecommendationTile(item: data.items[i], rank: i + 1),
            ],
          ],
        );
      },
    );
  }
}
