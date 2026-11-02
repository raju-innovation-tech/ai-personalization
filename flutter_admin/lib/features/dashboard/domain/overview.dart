int _asInt(dynamic value) => (value as num?)?.toInt() ?? 0;

class DayCount {
  const DayCount({required this.date, required this.count});

  final String date; // yyyy-MM-dd
  final int count;

  factory DayCount.fromJson(Map<String, dynamic> json) =>
      DayCount(date: json['date'] as String, count: _asInt(json['count']));
}

class NamedCount {
  const NamedCount({required this.name, required this.count});

  final String name;
  final int count;
}

class DashboardOverview {
  const DashboardOverview({
    required this.customers,
    required this.products,
    required this.activeProducts,
    required this.events,
    required this.events7d,
    required this.purchases30d,
    required this.recommendationsServed,
    required this.recommendationsServed7d,
    required this.impressions,
    required this.clicks,
    required this.ctr,
    required this.eventsByDay,
    required this.eventsByType,
    required this.topCategories,
    this.offersActive = 0,
    this.offersImpressions = 0,
    this.offersClicks = 0,
    this.offersRedemptions = 0,
    this.offersDiscountGiven = 0,
  });

  final int customers;
  final int products;
  final int activeProducts;
  final int events;
  final int events7d;
  final int purchases30d;
  final int recommendationsServed;
  final int recommendationsServed7d;
  final int impressions;
  final int clicks;
  final double? ctr;
  final List<DayCount> eventsByDay;
  final List<NamedCount> eventsByType;
  final List<NamedCount> topCategories;
  final int offersActive;
  final int offersImpressions;
  final int offersClicks;
  final int offersRedemptions;
  final double offersDiscountGiven;

  factory DashboardOverview.fromJson(Map<String, dynamic> json) {
    final totals = (json['totals'] as Map?)?.cast<String, dynamic>() ?? const {};
    final ctr = (json['recommendation_ctr_30d'] as Map?)?.cast<String, dynamic>() ?? const {};
    final offers = (json['offers'] as Map?)?.cast<String, dynamic>() ?? const {};

    List<Map<String, dynamic>> rows(String key) =>
        (json[key] as List<dynamic>? ?? const []).map((e) => (e as Map).cast<String, dynamic>()).toList();

    return DashboardOverview(
      customers: _asInt(totals['customers']),
      products: _asInt(totals['products']),
      activeProducts: _asInt(totals['active_products']),
      events: _asInt(totals['events']),
      events7d: _asInt(totals['events_7d']),
      purchases30d: _asInt(totals['purchases_30d']),
      recommendationsServed: _asInt(totals['recommendations_served']),
      recommendationsServed7d: _asInt(totals['recommendations_served_7d']),
      impressions: _asInt(ctr['impressions']),
      clicks: _asInt(ctr['clicks']),
      ctr: (ctr['ctr'] as num?)?.toDouble(),
      eventsByDay: rows('events_by_day').map(DayCount.fromJson).toList(),
      eventsByType: rows('events_by_type')
          .map((r) => NamedCount(name: r['event_type'] as String, count: _asInt(r['count'])))
          .toList(),
      topCategories: rows('top_categories')
          .map((r) => NamedCount(name: r['category'] as String, count: _asInt(r['interactions'])))
          .toList(),
      offersActive: _asInt(offers['active']),
      offersImpressions: _asInt(offers['impressions']),
      offersClicks: _asInt(offers['clicks']),
      offersRedemptions: _asInt(offers['redemptions']),
      offersDiscountGiven: (offers['discount_given'] as num?)?.toDouble() ?? 0,
    );
  }
}
