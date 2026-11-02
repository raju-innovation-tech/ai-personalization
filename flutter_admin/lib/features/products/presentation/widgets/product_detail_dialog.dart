import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../recommendations/presentation/providers/recommendations_providers.dart';
import '../../../recommendations/presentation/widgets/recommendation_tile.dart';
import '../../domain/product.dart';

/// Product details plus what the recommendation engine says about it:
/// similar products and frequently-bought-together.
class ProductDetailDialog extends ConsumerWidget {
  const ProductDetailDialog({super.key, required this.product});

  final Product product;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final similar = ref.watch(similarProductsProvider(product.productId));
    final together = ref.watch(boughtTogetherProvider(product.productId));

    return Dialog(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 720, maxHeight: 680),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: Text(product.name, style: textTheme.headlineSmall)),
                  IconButton(
                    tooltip: 'Close',
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
              Text(product.productId, style: textTheme.bodyMedium),
              const SizedBox(height: 12),
              Flexible(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          _InfoChip(Icons.sell_outlined, formatPrice(product.price)),
                          if (product.category != null) _InfoChip(Icons.category_outlined, product.category!),
                          if (product.brand != null) _InfoChip(Icons.business_outlined, product.brand!),
                          if (product.rating != null)
                            _InfoChip(Icons.star_rounded, product.rating!.toStringAsFixed(1), color: AppColors.warning),
                          _InfoChip(
                            product.inStock ? Icons.check_circle_outline : Icons.remove_circle_outline,
                            product.inStock ? 'In stock' : 'Out of stock',
                            color: product.inStock ? AppColors.success : AppColors.danger,
                          ),
                          for (final tag in product.tags) _InfoChip(Icons.tag, tag),
                        ],
                      ),
                      if (product.description != null && product.description!.isNotEmpty) ...[
                        const SizedBox(height: 12),
                        Text(product.description!, style: textTheme.bodyMedium),
                      ],
                      const SizedBox(height: 20),
                      Text('Similar products', style: textTheme.titleMedium),
                      const SizedBox(height: 4),
                      RecommendationList(result: similar, emptyText: 'No similar products found.'),
                      const SizedBox(height: 20),
                      Text('Frequently bought together', style: textTheme.titleMedium),
                      const SizedBox(height: 4),
                      RecommendationList(
                        result: together,
                        emptyText: 'Not enough purchase history for this product yet.',
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip(this.icon, this.label, {this.color});

  final IconData icon;
  final String label;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final tone = color ?? AppColors.primary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: tone),
          const SizedBox(width: 5),
          Text(label, style: TextStyle(fontSize: 12, color: tone, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
