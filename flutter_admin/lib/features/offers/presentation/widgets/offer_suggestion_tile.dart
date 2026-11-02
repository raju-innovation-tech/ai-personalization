import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../domain/offer.dart';

/// Small monospace pill showing a coupon code.
class CodeChip extends StatelessWidget {
  const CodeChip(this.code, {super.key});

  final String code;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.primary.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        code,
        style: const TextStyle(
          fontFamily: 'monospace',
          fontSize: 11.5,
          fontWeight: FontWeight.w700,
          color: AppColors.primary,
        ),
      ),
    );
  }
}

/// One offer served to a customer, with the reason the engine picked it.
class OfferSuggestionTile extends StatelessWidget {
  const OfferSuggestionTile({super.key, required this.offer});

  final OfferSuggestion offer;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final small = textTheme.bodyMedium?.copyWith(fontSize: 12);
    final conditions = [
      offer.headline,
      if (offer.minOrderValue != null) 'min order ${formatPrice(offer.minOrderValue)}',
      if (offer.endsAt != null) 'ends ${formatTimestamp(offer.endsAt!)}',
    ].join('  •  ');
    final preview = offer.discountPreview;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.local_offer_outlined, size: 20, color: AppColors.warning),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        offer.name,
                        style: textTheme.titleMedium?.copyWith(fontSize: 14),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 8),
                    CodeChip(offer.code),
                  ],
                ),
                const SizedBox(height: 2),
                Text(conditions, style: small, maxLines: 2, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 4),
                Text(offer.reason, style: textTheme.bodyMedium),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (preview != null && preview > 0)
                Text('−${formatPrice(preview)}', style: textTheme.titleMedium?.copyWith(fontSize: 14, color: AppColors.success)),
              if (offer.freeShipping) Text('Free shipping', style: small),
              const SizedBox(height: 4),
              Text('score ${offer.score.toStringAsFixed(2)}', style: small?.copyWith(fontSize: 11)),
            ],
          ),
        ],
      ),
    );
  }
}
