int _asInt(dynamic value) => (value as num?)?.toInt() ?? 0;

class SegmentRef {
  const SegmentRef({required this.key, required this.name, this.description, this.action});

  final String key;
  final String name;
  final String? description;
  final String? action;

  static SegmentRef? fromJson(dynamic json) {
    if (json is! Map<String, dynamic>) return null;
    return SegmentRef(
      key: json['key'] as String,
      name: json['name'] as String,
      description: json['description'] as String?,
      action: json['action'] as String?,
    );
  }
}

class CustomerStats {
  const CustomerStats({
    required this.events,
    required this.views,
    required this.cartAdds,
    required this.wishlistAdds,
    required this.activeDays,
    required this.orders,
    required this.itemsPurchased,
    required this.returns,
    required this.totalSpend,
    this.avgOrderValue,
    this.firstOrderAt,
    this.lastOrderAt,
    this.recencyDays,
  });

  final int events;
  final int views;
  final int cartAdds;
  final int wishlistAdds;
  final int activeDays;
  final int orders;
  final int itemsPurchased;
  final int returns;
  final double totalSpend;
  final double? avgOrderValue;
  final String? firstOrderAt;
  final String? lastOrderAt;
  final int? recencyDays;

  factory CustomerStats.fromJson(Map<String, dynamic> json) {
    return CustomerStats(
      events: _asInt(json['events']),
      views: _asInt(json['views']),
      cartAdds: _asInt(json['cart_adds']),
      wishlistAdds: _asInt(json['wishlist_adds']),
      activeDays: _asInt(json['active_days']),
      orders: _asInt(json['orders']),
      itemsPurchased: _asInt(json['items_purchased']),
      returns: _asInt(json['returns']),
      totalSpend: (json['total_spend'] as num?)?.toDouble() ?? 0,
      avgOrderValue: (json['avg_order_value'] as num?)?.toDouble(),
      firstOrderAt: json['first_order_at'] as String?,
      lastOrderAt: json['last_order_at'] as String?,
      recencyDays: (json['recency_days'] as num?)?.toInt(),
    );
  }
}

class Rfm {
  const Rfm({this.r, this.f, this.m, this.code});

  final int? r;
  final int? f;
  final int? m;
  final String? code;

  bool get isScored => r != null && f != null && m != null;

  factory Rfm.fromJson(Map<String, dynamic> json) {
    return Rfm(
      r: (json['r'] as num?)?.toInt(),
      f: (json['f'] as num?)?.toInt(),
      m: (json['m'] as num?)?.toInt(),
      code: json['code'] as String?,
    );
  }
}

class Customer {
  const Customer({
    required this.id,
    required this.stats,
    required this.rfm,
    this.segment,
    this.firstSeenAt,
    this.lastSeenAt,
    this.favoriteCategory,
    this.favoriteBrand,
    this.profileComputedAt,
  });

  final String id;
  final SegmentRef? segment;
  final String? firstSeenAt;
  final String? lastSeenAt;
  final CustomerStats stats;
  final Rfm rfm;
  final String? favoriteCategory;
  final String? favoriteBrand;
  final String? profileComputedAt;

  factory Customer.fromJson(Map<String, dynamic> json) {
    return Customer(
      id: json['customer_id'] as String,
      segment: SegmentRef.fromJson(json['segment']),
      firstSeenAt: json['first_seen_at'] as String?,
      lastSeenAt: json['last_seen_at'] as String?,
      stats: CustomerStats.fromJson(json['stats'] as Map<String, dynamic>? ?? const {}),
      rfm: Rfm.fromJson(json['rfm'] as Map<String, dynamic>? ?? const {}),
      favoriteCategory: json['favorite_category'] as String?,
      favoriteBrand: json['favorite_brand'] as String?,
      profileComputedAt: json['profile_computed_at'] as String?,
    );
  }
}

class CustomerPage {
  const CustomerPage({
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
    required this.totalPages,
  });

  final List<Customer> items;
  final int total;
  final int page;
  final int pageSize;
  final int totalPages;

  factory CustomerPage.fromJson(Map<String, dynamic> json) {
    return CustomerPage(
      items: (json['items'] as List<dynamic>? ?? const [])
          .map((e) => Customer.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: _asInt(json['total']),
      page: (json['page'] as num?)?.toInt() ?? 1,
      pageSize: (json['page_size'] as num?)?.toInt() ?? 20,
      totalPages: (json['total_pages'] as num?)?.toInt() ?? 1,
    );
  }
}

class TimelineEvent {
  const TimelineEvent({
    required this.eventType,
    required this.occurredAt,
    this.productId,
    this.productName,
    this.category,
    this.platform,
  });

  final String eventType;
  final String occurredAt;
  final String? productId;
  final String? productName;
  final String? category;
  final String? platform;

  factory TimelineEvent.fromJson(Map<String, dynamic> json) {
    return TimelineEvent(
      eventType: json['event_type'] as String,
      occurredAt: json['occurred_at'] as String? ?? '',
      productId: json['product_id'] as String?,
      productName: json['product_name'] as String?,
      category: json['category'] as String?,
      platform: json['platform'] as String?,
    );
  }
}

class TimelinePage {
  const TimelinePage({required this.items, required this.total, required this.page, required this.totalPages});

  final List<TimelineEvent> items;
  final int total;
  final int page;
  final int totalPages;

  factory TimelinePage.fromJson(Map<String, dynamic> json) {
    return TimelinePage(
      items: (json['items'] as List<dynamic>? ?? const [])
          .map((e) => TimelineEvent.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: _asInt(json['total']),
      page: (json['page'] as num?)?.toInt() ?? 1,
      totalPages: (json['total_pages'] as num?)?.toInt() ?? 1,
    );
  }
}

class TopSpender {
  const TopSpender({required this.id, required this.totalSpend, required this.orders, this.segment});

  final String id;
  final double totalSpend;
  final int orders;
  final SegmentRef? segment;
}

class CustomerOverview {
  const CustomerOverview({
    required this.customers,
    required this.buyers,
    required this.repeatBuyers,
    required this.activeCustomers,
    required this.newCustomers,
    required this.revenue,
    required this.orders,
    required this.activeDays,
    required this.topSpenders,
    this.repeatRate,
    this.avgOrderValue,
    this.profilesComputedAt,
  });

  final int customers;
  final int buyers;
  final int repeatBuyers;
  final double? repeatRate;
  final int activeCustomers;
  final int newCustomers;
  final double revenue;
  final int orders;
  final double? avgOrderValue;
  final int activeDays;
  final String? profilesComputedAt;
  final List<TopSpender> topSpenders;

  factory CustomerOverview.fromJson(Map<String, dynamic> json) {
    final totals = json['totals'] as Map<String, dynamic>? ?? const {};
    return CustomerOverview(
      customers: _asInt(totals['customers']),
      buyers: _asInt(totals['buyers']),
      repeatBuyers: _asInt(totals['repeat_buyers']),
      repeatRate: (totals['repeat_rate'] as num?)?.toDouble(),
      activeCustomers: _asInt(totals['active_customers']),
      newCustomers: _asInt(totals['new_customers']),
      revenue: (totals['revenue'] as num?)?.toDouble() ?? 0,
      orders: _asInt(totals['orders']),
      avgOrderValue: (totals['avg_order_value'] as num?)?.toDouble(),
      activeDays: (json['active_days'] as num?)?.toInt() ?? 30,
      profilesComputedAt: json['profiles_computed_at'] as String?,
      topSpenders: (json['top_spenders'] as List<dynamic>? ?? const []).map((e) {
        final row = e as Map<String, dynamic>;
        return TopSpender(
          id: row['customer_id'] as String,
          totalSpend: (row['total_spend'] as num?)?.toDouble() ?? 0,
          orders: _asInt(row['orders']),
          segment: SegmentRef.fromJson(row['segment']),
        );
      }).toList(),
    );
  }
}

/// What the customer list is currently showing.
class CustomerQuery {
  const CustomerQuery({
    this.search = '',
    this.segment,
    this.sort = 'last_seen',
    this.descending = true,
    this.page = 1,
  });

  final String search;
  final String? segment;
  final String sort; // last_seen | spend | orders | recency | rfm
  final bool descending;
  final int page;

  static const int pageSize = 20;

  /// Changing any filter goes back to page 1 unless a page is given explicitly.
  CustomerQuery copyWith({
    String? search,
    String? segment,
    bool clearSegment = false,
    String? sort,
    bool? descending,
    int? page,
  }) {
    return CustomerQuery(
      search: search ?? this.search,
      segment: clearSegment ? null : (segment ?? this.segment),
      sort: sort ?? this.sort,
      descending: descending ?? this.descending,
      page: page ?? 1,
    );
  }
}
