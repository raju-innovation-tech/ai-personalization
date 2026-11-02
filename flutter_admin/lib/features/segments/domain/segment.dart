int _asInt(dynamic value) => (value as num?)?.toInt() ?? 0;

class SegmentInfo {
  const SegmentInfo({
    required this.key,
    required this.name,
    required this.description,
    required this.action,
    required this.customers,
    required this.share,
    required this.revenue,
    required this.revenueShare,
    this.avgSpend,
    this.avgRecencyDays,
    this.avgOrders,
  });

  final String key;
  final String name;
  final String description;
  final String action;
  final int customers;
  final double share;
  final double revenue;
  final double revenueShare;
  final double? avgSpend;
  final double? avgRecencyDays;
  final double? avgOrders;

  factory SegmentInfo.fromJson(Map<String, dynamic> json) {
    return SegmentInfo(
      key: json['key'] as String,
      name: json['name'] as String,
      description: json['description'] as String? ?? '',
      action: json['action'] as String? ?? '',
      customers: _asInt(json['customers']),
      share: (json['share'] as num?)?.toDouble() ?? 0,
      revenue: (json['revenue'] as num?)?.toDouble() ?? 0,
      revenueShare: (json['revenue_share'] as num?)?.toDouble() ?? 0,
      avgSpend: (json['avg_spend'] as num?)?.toDouble(),
      avgRecencyDays: (json['avg_recency_days'] as num?)?.toDouble(),
      avgOrders: (json['avg_orders'] as num?)?.toDouble(),
    );
  }
}

class RfmCell {
  const RfmCell({required this.r, required this.f, required this.count});

  final int r;
  final int f;
  final int count;
}

class SegmentOverview {
  const SegmentOverview({
    required this.totalCustomers,
    required this.segments,
    required this.grid,
    this.profilesComputedAt,
  });

  final int totalCustomers;
  final String? profilesComputedAt;
  final List<SegmentInfo> segments;
  final List<RfmCell> grid;

  factory SegmentOverview.fromJson(Map<String, dynamic> json) {
    return SegmentOverview(
      totalCustomers: _asInt(json['total_customers']),
      profilesComputedAt: json['profiles_computed_at'] as String?,
      segments: (json['segments'] as List<dynamic>? ?? const [])
          .map((e) => SegmentInfo.fromJson(e as Map<String, dynamic>))
          .toList(),
      grid: (json['rfm_grid'] as List<dynamic>? ?? const []).map((e) {
        final cell = e as Map<String, dynamic>;
        return RfmCell(r: _asInt(cell['r']), f: _asInt(cell['f']), count: _asInt(cell['count']));
      }).toList(),
    );
  }
}
