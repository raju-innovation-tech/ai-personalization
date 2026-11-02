import 'package:flutter/material.dart';

/// One colour per RFM segment, shared by the chips, cards and charts.
Color segmentColor(String? key) {
  switch (key) {
    case 'champions':
      return const Color(0xFF16A34A);
    case 'loyal':
      return const Color(0xFF0D9488);
    case 'potential_loyalist':
      return const Color(0xFF2563EB);
    case 'new_customer':
      return const Color(0xFF4F46E5);
    case 'need_attention':
      return const Color(0xFFD97706);
    case 'about_to_sleep':
      return const Color(0xFFEA580C);
    case 'cant_lose':
      return const Color(0xFFDC2626);
    case 'at_risk':
      return const Color(0xFFE11D48);
    case 'hibernating':
      return const Color(0xFF7C3AED);
    case 'lost':
      return const Color(0xFF4B5563);
    case 'prospect':
      return const Color(0xFF0891B2);
    default: // inactive, unknown, not scored yet
      return const Color(0xFF9CA3AF);
  }
}

class SegmentChip extends StatelessWidget {
  const SegmentChip({super.key, required this.segmentKey, required this.label});

  final String? segmentKey;
  final String label;

  @override
  Widget build(BuildContext context) {
    final color = segmentColor(segmentKey);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.13),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontSize: 11.5, fontWeight: FontWeight.w700),
      ),
    );
  }
}
