int _asInt(dynamic value) => (value as num?)?.toInt() ?? 0;

class ChecklistItem {
  const ChecklistItem({required this.key, required this.title, required this.status, required this.detail});

  final String key;
  final String title;
  final String status; // ok | warning | todo
  final String detail;
}

class AccountInfo {
  const AccountInfo({required this.email, required this.fullName, required this.role, required this.isActive});

  final String email;
  final String fullName;
  final String role;
  final bool isActive;
}

class IntegrationStatus {
  const IntegrationStatus({
    required this.score,
    required this.checklist,
    required this.eventsTotal,
    required this.events24h,
    required this.events7d,
    required this.eventTypes30d,
    required this.products,
    required this.activeProducts,
    required this.outOfStock,
    required this.productEvents30d,
    required this.unknownProductEvents30d,
    required this.purchaseEvents30d,
    required this.purchasesWithoutSession30d,
    required this.recommendationsServed,
    required this.redemptions,
    this.lastEventAt,
    this.catalogUpdatedAt,
    this.unknownProductRate,
    this.purchasesWithoutSessionRate,
    this.profilesComputedAt,
    this.lastRecommendationAt,
    this.lastRedemptionAt,
    this.accounts,
  });

  final double score;
  final List<ChecklistItem> checklist;

  final int eventsTotal;
  final int events24h;
  final int events7d;
  final int eventTypes30d;
  final String? lastEventAt;

  final int products;
  final int activeProducts;
  final int outOfStock;
  final String? catalogUpdatedAt;

  final int productEvents30d;
  final int unknownProductEvents30d;
  final double? unknownProductRate;
  final int purchaseEvents30d;
  final int purchasesWithoutSession30d;
  final double? purchasesWithoutSessionRate;

  final String? profilesComputedAt;
  final int recommendationsServed;
  final String? lastRecommendationAt;
  final int redemptions;
  final String? lastRedemptionAt;

  /// Only admins receive the account list.
  final List<AccountInfo>? accounts;

  int get doneCount => checklist.where((c) => c.status == 'ok').length;

  factory IntegrationStatus.fromJson(Map<String, dynamic> json) {
    final events = json['events'] as Map<String, dynamic>? ?? const {};
    final catalog = json['catalog'] as Map<String, dynamic>? ?? const {};
    final quality = json['data_quality'] as Map<String, dynamic>? ?? const {};
    final profiles = json['profiles'] as Map<String, dynamic>? ?? const {};
    final reco = json['recommendations'] as Map<String, dynamic>? ?? const {};
    final checkout = json['checkout'] as Map<String, dynamic>? ?? const {};
    final accounts = json['accounts'] as List<dynamic>?;

    return IntegrationStatus(
      score: (json['score'] as num?)?.toDouble() ?? 0,
      checklist: (json['checklist'] as List<dynamic>? ?? const []).map((e) {
        final row = e as Map<String, dynamic>;
        return ChecklistItem(
          key: row['key'] as String,
          title: row['title'] as String? ?? '',
          status: row['status'] as String? ?? 'todo',
          detail: row['detail'] as String? ?? '',
        );
      }).toList(),
      eventsTotal: _asInt(events['total']),
      events24h: _asInt(events['last_24h']),
      events7d: _asInt(events['last_7d']),
      eventTypes30d: _asInt(events['event_types_30d']),
      lastEventAt: events['last_event_at'] as String?,
      products: _asInt(catalog['products']),
      activeProducts: _asInt(catalog['active']),
      outOfStock: _asInt(catalog['out_of_stock']),
      catalogUpdatedAt: catalog['last_updated_at'] as String?,
      productEvents30d: _asInt(quality['product_events_30d']),
      unknownProductEvents30d: _asInt(quality['unknown_product_events_30d']),
      unknownProductRate: (quality['unknown_product_rate'] as num?)?.toDouble(),
      purchaseEvents30d: _asInt(quality['purchase_events_30d']),
      purchasesWithoutSession30d: _asInt(quality['purchases_without_session_30d']),
      purchasesWithoutSessionRate: (quality['purchases_without_session_rate'] as num?)?.toDouble(),
      profilesComputedAt: profiles['last_computed_at'] as String?,
      recommendationsServed: _asInt(reco['served_total']),
      lastRecommendationAt: reco['last_served_at'] as String?,
      redemptions: _asInt(checkout['redemptions_total']),
      lastRedemptionAt: checkout['last_redemption_at'] as String?,
      accounts: accounts
          ?.map((e) {
            final row = e as Map<String, dynamic>;
            return AccountInfo(
              email: row['email'] as String,
              fullName: row['full_name'] as String? ?? '',
              role: row['role'] as String? ?? '',
              isActive: row['is_active'] as bool? ?? true,
            );
          })
          .toList(),
    );
  }
}
