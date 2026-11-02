int _asInt(dynamic value) => (value as num?)?.toInt() ?? 0;
double _asDouble(dynamic value) => (value as num?)?.toDouble() ?? 0;

class Kpi {
  const Kpi({required this.value, this.previous, this.change});

  final double value;
  final double? previous;
  final double? change; // relative change vs the previous period, e.g. 0.12 = +12%

  factory Kpi.fromJson(Map<String, dynamic> json) => Kpi(
        value: _asDouble(json['value']),
        previous: (json['previous'] as num?)?.toDouble(),
        change: (json['change'] as num?)?.toDouble(),
      );
}

class DailyPoint {
  const DailyPoint({
    required this.date,
    required this.events,
    required this.activeCustomers,
    required this.newCustomers,
    required this.orders,
    required this.revenue,
    required this.recViews,
    required this.recClicks,
    required this.recsServed,
    required this.offerImpressions,
    required this.offerClicks,
    required this.offerRedemptions,
    required this.offerDiscount,
  });

  final String date; // yyyy-MM-dd
  final int events;
  final int activeCustomers;
  final int newCustomers;
  final int orders;
  final double revenue;
  final int recViews;
  final int recClicks;
  final int recsServed;
  final int offerImpressions;
  final int offerClicks;
  final int offerRedemptions;
  final double offerDiscount;

  factory DailyPoint.fromJson(Map<String, dynamic> json) => DailyPoint(
        date: json['date'] as String,
        events: _asInt(json['events']),
        activeCustomers: _asInt(json['active_customers']),
        newCustomers: _asInt(json['new_customers']),
        orders: _asInt(json['orders']),
        revenue: _asDouble(json['revenue']),
        recViews: _asInt(json['rec_views']),
        recClicks: _asInt(json['rec_clicks']),
        recsServed: _asInt(json['recs_served']),
        offerImpressions: _asInt(json['offer_impressions']),
        offerClicks: _asInt(json['offer_clicks']),
        offerRedemptions: _asInt(json['offer_redemptions']),
        offerDiscount: _asDouble(json['offer_discount']),
      );
}

class FunnelStep {
  const FunnelStep({required this.step, required this.label, required this.customers, this.rateFromStart, this.rateFromPrevious});

  final String step;
  final String label;
  final int customers;
  final double? rateFromStart;
  final double? rateFromPrevious;

  factory FunnelStep.fromJson(Map<String, dynamic> json) => FunnelStep(
        step: json['step'] as String,
        label: json['label'] as String? ?? json['step'] as String,
        customers: _asInt(json['customers']),
        rateFromStart: (json['rate_from_start'] as num?)?.toDouble(),
        rateFromPrevious: (json['rate_from_previous'] as num?)?.toDouble(),
      );
}

class TopProduct {
  const TopProduct({
    required this.productId,
    required this.name,
    required this.units,
    required this.revenue,
    required this.views,
    this.category,
  });

  final String productId;
  final String name;
  final String? category;
  final int units;
  final double revenue;
  final int views;

  factory TopProduct.fromJson(Map<String, dynamic> json) => TopProduct(
        productId: json['product_id'] as String,
        name: json['name'] as String? ?? json['product_id'] as String,
        category: json['category'] as String?,
        units: _asInt(json['units']),
        revenue: _asDouble(json['revenue']),
        views: _asInt(json['views']),
      );
}

class TopCategory {
  const TopCategory({required this.category, required this.revenue, required this.share});

  final String category;
  final double revenue;
  final double share;
}

class PlatformShare {
  const PlatformShare({required this.platform, required this.events, required this.share});

  final String platform;
  final int events;
  final double share;
}

class AnalyticsReport {
  const AnalyticsReport({
    required this.days,
    required this.from,
    required this.to,
    required this.kpis,
    required this.daily,
    required this.funnel,
    required this.topProducts,
    required this.topCategories,
    required this.platforms,
  });

  final int days;
  final String from;
  final String to;
  final Map<String, Kpi> kpis;
  final List<DailyPoint> daily;
  final List<FunnelStep> funnel;
  final List<TopProduct> topProducts;
  final List<TopCategory> topCategories;
  final List<PlatformShare> platforms;

  Kpi kpi(String key) => kpis[key] ?? const Kpi(value: 0);

  factory AnalyticsReport.fromJson(Map<String, dynamic> json) {
    List<Map<String, dynamic>> rows(String key) =>
        (json[key] as List<dynamic>? ?? const []).map((e) => e as Map<String, dynamic>).toList();

    final kpiJson = json['kpis'] as Map<String, dynamic>? ?? const {};
    return AnalyticsReport(
      days: _asInt(json['days']),
      from: json['from'] as String? ?? '',
      to: json['to'] as String? ?? '',
      kpis: kpiJson.map((key, value) => MapEntry(key, Kpi.fromJson(value as Map<String, dynamic>))),
      daily: rows('daily').map(DailyPoint.fromJson).toList(),
      funnel: rows('funnel').map(FunnelStep.fromJson).toList(),
      topProducts: rows('top_products').map(TopProduct.fromJson).toList(),
      topCategories: rows('top_categories')
          .map((r) => TopCategory(
                category: r['category'] as String,
                revenue: _asDouble(r['revenue']),
                share: _asDouble(r['share']),
              ))
          .toList(),
      platforms: rows('platforms')
          .map((r) => PlatformShare(
                platform: r['platform'] as String,
                events: _asInt(r['events']),
                share: _asDouble(r['share']),
              ))
          .toList(),
    );
  }
}
