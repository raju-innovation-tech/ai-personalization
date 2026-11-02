int _asInt(dynamic value) => (value as num?)?.toInt() ?? 0;

class RecommendationItem {
  const RecommendationItem({
    required this.productId,
    required this.name,
    required this.score,
    required this.reason,
    required this.algorithm,
    this.category,
    this.brand,
    this.price,
    this.rating,
    this.inStock = true,
  });

  final String productId;
  final String name;
  final String? category;
  final String? brand;
  final double? price;
  final double? rating;
  final bool inStock;
  final double score;
  final String reason;
  final String algorithm;

  factory RecommendationItem.fromJson(Map<String, dynamic> json) {
    return RecommendationItem(
      productId: json['product_id'] as String,
      name: json['name'] as String,
      category: json['category'] as String?,
      brand: json['brand'] as String?,
      price: (json['price'] as num?)?.toDouble(),
      rating: (json['rating'] as num?)?.toDouble(),
      inStock: json['in_stock'] as bool? ?? true,
      score: (json['score'] as num?)?.toDouble() ?? 0,
      reason: json['reason'] as String? ?? '',
      algorithm: json['algorithm'] as String? ?? '',
    );
  }
}

class RecommendationResult {
  const RecommendationResult({required this.algorithm, required this.items, this.personalized});

  final String algorithm;
  final List<RecommendationItem> items;
  final bool? personalized;

  factory RecommendationResult.fromJson(Map<String, dynamic> json) {
    return RecommendationResult(
      algorithm: json['algorithm'] as String? ?? '',
      items: (json['items'] as List<dynamic>? ?? const [])
          .map((e) => RecommendationItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      personalized: json['personalized'] as bool?,
    );
  }
}

class AlgorithmUsage {
  const AlgorithmUsage({required this.total, required this.last7d});

  final int total;
  final int last7d;
}

class EngineStatus {
  const EngineStatus({
    required this.builtAt,
    required this.products,
    required this.customersWithHistory,
    required this.interactions,
    required this.baskets,
    required this.fbtPairs,
    required this.servedTotal,
    required this.served7d,
    required this.lookbackDays,
    required this.servedByAlgorithm,
  });

  final String builtAt;
  final int products;
  final int customersWithHistory;
  final int interactions;
  final int baskets;
  final int fbtPairs;
  final int servedTotal;
  final int served7d;
  final int lookbackDays;
  final Map<String, AlgorithmUsage> servedByAlgorithm;

  factory EngineStatus.fromJson(Map<String, dynamic> json) {
    final usageJson = json['served_by_algorithm'] as Map<String, dynamic>? ?? const {};
    return EngineStatus(
      builtAt: json['built_at'] as String? ?? '',
      products: _asInt(json['products']),
      customersWithHistory: _asInt(json['customers_with_history']),
      interactions: _asInt(json['interactions']),
      baskets: _asInt(json['baskets']),
      fbtPairs: _asInt(json['fbt_pairs']),
      servedTotal: _asInt(json['served_total']),
      served7d: _asInt(json['served_7d']),
      lookbackDays: _asInt(json['lookback_days']),
      servedByAlgorithm: usageJson.map((key, value) {
        final usage = value as Map<String, dynamic>;
        return MapEntry(key, AlgorithmUsage(total: _asInt(usage['total']), last7d: _asInt(usage['last_7d'])));
      }),
    );
  }
}
