int _asInt(dynamic value) => (value as num?)?.toInt() ?? 0;
double _asDouble(dynamic value) => (value as num?)?.toDouble() ?? 0.0;

/// Info about one ML model from the registry.
class MlModelInfo {
  const MlModelInfo({
    required this.name,
    required this.version,
    required this.description,
    required this.trainedAt,
    required this.customerCount,
    required this.avgScore,
    required this.highRiskCount,
    required this.estimatedAuc,
  });

  final String name;
  final String version;
  final String description;
  final String trainedAt;
  final int customerCount;
  final double avgScore;
  final int highRiskCount;
  final double estimatedAuc;

  factory MlModelInfo.fromJson(Map<String, dynamic> json) => MlModelInfo(
        name: json['name'] as String? ?? '',
        version: json['version'] as String? ?? '1.0',
        description: json['description'] as String? ?? '',
        trainedAt: json['trained_at'] as String? ?? '',
        customerCount: _asInt(json['customer_count']),
        avgScore: _asDouble(json['avg_score']),
        highRiskCount: _asInt(json['high_risk_count']),
        estimatedAuc: _asDouble(json['estimated_auc']),
      );
}

/// Per-customer prediction (purchase probability or churn risk).
class CustomerPrediction {
  const CustomerPrediction({
    required this.userId,
    required this.score,
    required this.label,
    required this.confidence,
    required this.explanation,
  });

  final String userId;
  final double score;
  final String label; // low | medium | high
  final double confidence;
  final String explanation;

  factory CustomerPrediction.fromJson(String userId, Map<String, dynamic> json) =>
      CustomerPrediction(
        userId: userId,
        score: _asDouble(json['score']),
        label: json['label'] as String? ?? 'low',
        confidence: _asDouble(json['confidence']),
        explanation: json['explanation'] as String? ?? '',
      );
}

/// Offer response prediction for one customer.
class OfferResponsePrediction {
  const OfferResponsePrediction({
    required this.userId,
    required this.recommendedOfferType,
    required this.scores,
    required this.explanation,
  });

  final String userId;
  final String recommendedOfferType;
  final Map<String, double> scores;
  final String explanation;

  factory OfferResponsePrediction.fromJson(String userId, Map<String, dynamic> json) {
    final rawScores = json['scores'] as Map<String, dynamic>? ?? {};
    return OfferResponsePrediction(
      userId: userId,
      recommendedOfferType: json['recommended_offer_type'] as String? ?? 'discount',
      scores: rawScores.map((k, v) => MapEntry(k, _asDouble(v))),
      explanation: json['explanation'] as String? ?? '',
    );
  }
}

/// Combined ML predictions for one customer.
class CustomerMlProfile {
  const CustomerMlProfile({
    required this.userId,
    this.purchaseProbability,
    this.churnRisk,
    this.offerResponse,
  });

  final String userId;
  final CustomerPrediction? purchaseProbability;
  final CustomerPrediction? churnRisk;
  final OfferResponsePrediction? offerResponse;

  factory CustomerMlProfile.fromJson(Map<String, dynamic> json) {
    final userId = json['user_id'] as String? ?? '';
    CustomerPrediction? parsePred(String key) {
      final d = json[key] as Map<String, dynamic>?;
      return d == null ? null : CustomerPrediction.fromJson(userId, d);
    }

    final offerJson = json['offer_response'] as Map<String, dynamic>?;
    return CustomerMlProfile(
      userId: userId,
      purchaseProbability: parsePred('purchase_probability'),
      churnRisk: parsePred('churn_risk'),
      offerResponse: offerJson == null ? null : OfferResponsePrediction.fromJson(userId, offerJson),
    );
  }
}

/// Top-risk customer entry.
class TopRiskCustomer {
  const TopRiskCustomer({
    required this.userId,
    required this.score,
    required this.label,
    required this.explanation,
  });

  final String userId;
  final double score;
  final String label;
  final String explanation;

  factory TopRiskCustomer.fromJson(Map<String, dynamic> json) => TopRiskCustomer(
        userId: json['user_id'] as String? ?? '',
        score: _asDouble(json['score']),
        label: json['label'] as String? ?? 'medium',
        explanation: json['explanation'] as String? ?? '',
      );
}

/// Score distribution histogram for a model.
class ScoreDistribution {
  const ScoreDistribution({
    required this.model,
    required this.totalScored,
    required this.distribution,
  });

  final String model;
  final int totalScored;
  final Map<String, int> distribution;

  factory ScoreDistribution.fromJson(Map<String, dynamic> json) {
    final dist = json['distribution'] as Map<String, dynamic>? ?? {};
    return ScoreDistribution(
      model: json['model'] as String? ?? '',
      totalScored: _asInt(json['total_scored']),
      distribution: dist.map((k, v) => MapEntry(k, _asInt(v))),
    );
  }
}
