import '../../../core/utils/formatters.dart';

int _asInt(dynamic value) => (value as num?)?.toInt() ?? 0;

const List<String> kOfferTypes = ['percent_off', 'fixed_off', 'free_shipping'];

String offerTypeLabel(String type) {
  switch (type) {
    case 'percent_off':
      return 'Percentage off';
    case 'fixed_off':
      return 'Fixed amount off';
    case 'free_shipping':
      return 'Free shipping';
    default:
      return humanize(type);
  }
}

/// "10% off (max ₹500)", "₹500 off", "Free shipping"
String offerHeadline({required String type, required double value, double? maxDiscount}) {
  switch (type) {
    case 'percent_off':
      final pct = value == value.roundToDouble() ? value.toInt().toString() : value.toStringAsFixed(1);
      return maxDiscount == null ? '$pct% off' : '$pct% off (max ${formatPrice(maxDiscount)})';
    case 'fixed_off':
      return '${formatPrice(value)} off';
    case 'free_shipping':
      return 'Free shipping';
    default:
      return humanize(type);
  }
}

class OfferStatsData {
  const OfferStatsData({
    required this.impressions,
    required this.clicks,
    required this.redemptions,
    required this.discountGiven,
    required this.revenue,
    this.ctr,
    this.redemptionRate,
    this.remaining,
  });

  final int impressions;
  final int clicks;
  final int redemptions;
  final double? ctr;
  final double? redemptionRate;
  final double discountGiven;
  final double revenue;
  final int? remaining;

  factory OfferStatsData.fromJson(Map<String, dynamic> json) {
    return OfferStatsData(
      impressions: _asInt(json['impressions']),
      clicks: _asInt(json['clicks']),
      redemptions: _asInt(json['redemptions']),
      ctr: (json['ctr'] as num?)?.toDouble(),
      redemptionRate: (json['redemption_rate'] as num?)?.toDouble(),
      discountGiven: (json['discount_given'] as num?)?.toDouble() ?? 0,
      revenue: (json['revenue'] as num?)?.toDouble() ?? 0,
      remaining: (json['remaining'] as num?)?.toInt(),
    );
  }
}

class Offer {
  const Offer({
    required this.id,
    required this.code,
    required this.name,
    required this.offerType,
    required this.value,
    required this.status,
    required this.effectiveStatus,
    required this.maxPerCustomer,
    required this.priority,
    required this.targetSegments,
    required this.targetCategories,
    required this.stats,
    this.description,
    this.maxDiscount,
    this.minOrderValue,
    this.maxRedemptions,
    this.startsAt,
    this.endsAt,
  });

  final String id;
  final String code;
  final String name;
  final String? description;
  final String offerType;
  final double value;
  final double? maxDiscount;
  final double? minOrderValue;
  final int? maxRedemptions;
  final int maxPerCustomer;
  final String status;
  final String effectiveStatus; // draft | scheduled | active | expired | paused | ended
  final String? startsAt;
  final String? endsAt;
  final List<String> targetSegments;
  final List<String> targetCategories;
  final int priority;
  final OfferStatsData stats;

  String get headline => offerHeadline(type: offerType, value: value, maxDiscount: maxDiscount);

  factory Offer.fromJson(Map<String, dynamic> json) {
    List<String> strings(String key) =>
        (json[key] as List<dynamic>? ?? const []).map((e) => e.toString()).toList();

    return Offer(
      id: json['id'] as String,
      code: json['code'] as String,
      name: json['name'] as String,
      description: json['description'] as String?,
      offerType: json['offer_type'] as String,
      value: (json['value'] as num?)?.toDouble() ?? 0,
      maxDiscount: (json['max_discount'] as num?)?.toDouble(),
      minOrderValue: (json['min_order_value'] as num?)?.toDouble(),
      maxRedemptions: (json['max_redemptions'] as num?)?.toInt(),
      maxPerCustomer: (json['max_per_customer'] as num?)?.toInt() ?? 1,
      status: json['status'] as String? ?? 'draft',
      effectiveStatus: json['effective_status'] as String? ?? (json['status'] as String? ?? 'draft'),
      startsAt: json['starts_at'] as String?,
      endsAt: json['ends_at'] as String?,
      targetSegments: strings('target_segments'),
      targetCategories: strings('target_categories'),
      priority: (json['priority'] as num?)?.toInt() ?? 50,
      stats: OfferStatsData.fromJson(json['stats'] as Map<String, dynamic>? ?? const {}),
    );
  }
}

class OfferPage {
  const OfferPage({
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
    required this.totalPages,
  });

  final List<Offer> items;
  final int total;
  final int page;
  final int pageSize;
  final int totalPages;

  factory OfferPage.fromJson(Map<String, dynamic> json) {
    return OfferPage(
      items: (json['items'] as List<dynamic>? ?? const [])
          .map((e) => Offer.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: _asInt(json['total']),
      page: (json['page'] as num?)?.toInt() ?? 1,
      pageSize: (json['page_size'] as num?)?.toInt() ?? 10,
      totalPages: (json['total_pages'] as num?)?.toInt() ?? 1,
    );
  }
}

class OfferTotals {
  const OfferTotals({
    required this.offers,
    required this.byStatus,
    required this.activeNow,
    required this.impressions,
    required this.clicks,
    required this.redemptions,
    required this.discountGiven,
    required this.revenue,
    required this.redemptions30d,
    this.ctr,
    this.redemptionRate,
  });

  final int offers;
  final Map<String, int> byStatus;
  final int activeNow;
  final int impressions;
  final int clicks;
  final int redemptions;
  final double discountGiven;
  final double revenue;
  final double? ctr;
  final double? redemptionRate;
  final int redemptions30d;

  factory OfferTotals.fromJson(Map<String, dynamic> json) {
    final all = json['all_time'] as Map<String, dynamic>? ?? const {};
    final recent = json['last_30d'] as Map<String, dynamic>? ?? const {};
    final status = json['by_status'] as Map<String, dynamic>? ?? const {};
    return OfferTotals(
      offers: _asInt(json['offers']),
      byStatus: status.map((key, value) => MapEntry(key, _asInt(value))),
      activeNow: _asInt(json['active_now']),
      impressions: _asInt(all['impressions']),
      clicks: _asInt(all['clicks']),
      redemptions: _asInt(all['redemptions']),
      discountGiven: (all['discount_given'] as num?)?.toDouble() ?? 0,
      revenue: (all['revenue'] as num?)?.toDouble() ?? 0,
      ctr: (all['ctr'] as num?)?.toDouble(),
      redemptionRate: (all['redemption_rate'] as num?)?.toDouble(),
      redemptions30d: _asInt(recent['redemptions']),
    );
  }
}

/// An offer as served to one customer (`GET /offers/user/{id}`).
class OfferSuggestion {
  const OfferSuggestion({
    required this.id,
    required this.code,
    required this.name,
    required this.offerType,
    required this.value,
    required this.score,
    required this.reason,
    required this.freeShipping,
    this.description,
    this.maxDiscount,
    this.minOrderValue,
    this.endsAt,
    this.discountPreview,
  });

  final String id;
  final String code;
  final String name;
  final String? description;
  final String offerType;
  final double value;
  final double? maxDiscount;
  final double? minOrderValue;
  final String? endsAt;
  final double score;
  final String reason;
  final double? discountPreview;
  final bool freeShipping;

  String get headline => offerHeadline(type: offerType, value: value, maxDiscount: maxDiscount);

  factory OfferSuggestion.fromJson(Map<String, dynamic> json) {
    return OfferSuggestion(
      id: json['id'] as String,
      code: json['code'] as String,
      name: json['name'] as String,
      description: json['description'] as String?,
      offerType: json['offer_type'] as String,
      value: (json['value'] as num?)?.toDouble() ?? 0,
      maxDiscount: (json['max_discount'] as num?)?.toDouble(),
      minOrderValue: (json['min_order_value'] as num?)?.toDouble(),
      endsAt: json['ends_at'] as String?,
      score: (json['score'] as num?)?.toDouble() ?? 0,
      reason: json['reason'] as String? ?? '',
      discountPreview: (json['discount_preview'] as num?)?.toDouble(),
      freeShipping: json['free_shipping'] as bool? ?? false,
    );
  }
}

/// The create / edit form's payload.
class OfferInput {
  const OfferInput({
    required this.code,
    required this.name,
    required this.offerType,
    required this.value,
    required this.maxPerCustomer,
    required this.priority,
    this.description,
    this.maxDiscount,
    this.minOrderValue,
    this.maxRedemptions,
    this.startsAt,
    this.endsAt,
    this.targetSegments = const [],
    this.targetCategories = const [],
  });

  final String code;
  final String name;
  final String? description;
  final String offerType;
  final double value;
  final double? maxDiscount;
  final double? minOrderValue;
  final int? maxRedemptions;
  final int maxPerCustomer;
  final DateTime? startsAt;
  final DateTime? endsAt;
  final List<String> targetSegments;
  final List<String> targetCategories;
  final int priority;

  Map<String, dynamic> toJson() {
    final note = description?.trim();
    return {
      'code': code.trim().toUpperCase(),
      'name': name.trim(),
      'description': (note == null || note.isEmpty) ? null : note,
      'offer_type': offerType,
      'value': offerType == 'free_shipping' ? 0 : value,
      'max_discount': maxDiscount,
      'min_order_value': minOrderValue,
      'max_redemptions': maxRedemptions,
      'max_per_customer': maxPerCustomer,
      'starts_at': startsAt?.toUtc().toIso8601String(),
      'ends_at': endsAt?.toUtc().toIso8601String(),
      'target_segments': targetSegments,
      'target_categories': targetCategories,
      'priority': priority,
    };
  }
}

/// What the offers list is currently showing.
class OfferQuery {
  const OfferQuery({this.status, this.search = '', this.page = 1});

  final String? status; // draft | active | paused | ended | null = all
  final String search;
  final int page;

  static const int pageSize = 10;

  /// Changing a filter goes back to page 1 unless a page is given explicitly.
  OfferQuery copyWith({String? status, bool clearStatus = false, String? search, int? page}) {
    return OfferQuery(
      status: clearStatus ? null : (status ?? this.status),
      search: search ?? this.search,
      page: page ?? 1,
    );
  }
}
