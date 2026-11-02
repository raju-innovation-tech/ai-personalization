import '../../../core/utils/formatters.dart';

int _asInt(dynamic value) => (value as num?)?.toInt() ?? 0;
double _asDouble(dynamic value) => (value as num?)?.toDouble() ?? 0;

const List<String> kExperimentKinds = ['recommendations', 'offers'];
const List<String> kExperimentMetrics = ['conversion', 'click', 'revenue'];
const List<String> kRecommendationStrategies = ['hybrid', 'content', 'collaborative', 'popular'];

String experimentKindLabel(String kind) => kind == 'offers' ? 'Offers' : 'Recommendations';

String metricLabel(String metric) {
  switch (metric) {
    case 'click':
      return 'Click rate';
    case 'revenue':
      return 'Revenue per customer';
    default:
      return 'Purchase conversion';
  }
}

String strategyLabel(String strategy) {
  switch (strategy) {
    case 'hybrid':
      return 'Hybrid (default blend)';
    case 'content':
      return 'Content-based only';
    case 'collaborative':
      return 'Collaborative only';
    case 'popular':
      return 'Popular (not personalised)';
    default:
      return humanize(strategy);
  }
}

/// "p = 0.0123" / "p < 0.001"
String formatPValue(double p) => p < 0.001 ? 'p < 0.001' : 'p = ${p.toStringAsFixed(3)}';

class ExperimentVariant {
  const ExperimentVariant({
    required this.key,
    required this.name,
    required this.weight,
    required this.share,
    required this.config,
    required this.isControl,
    required this.exposed,
  });

  final String key;
  final String name;
  final double weight;
  final double share;
  final Map<String, dynamic> config;
  final bool isControl;
  final int exposed;

  /// What this variant changes, in words.
  String describe(String kind) {
    if (kind == 'recommendations') {
      return strategyLabel(config['strategy'] as String? ?? 'hybrid');
    }
    final codes = config['offer_codes'];
    if (codes is List) {
      return codes.isEmpty ? 'No offers (holdout)' : 'Only ${codes.join(', ')}';
    }
    return 'All offers (normal behaviour)';
  }

  factory ExperimentVariant.fromJson(Map<String, dynamic> json) {
    return ExperimentVariant(
      key: json['key'] as String,
      name: json['name'] as String,
      weight: _asDouble(json['weight']),
      share: _asDouble(json['share']),
      config: json['config'] as Map<String, dynamic>? ?? const {},
      isControl: json['is_control'] as bool? ?? false,
      exposed: _asInt(json['exposed']),
    );
  }
}

class Experiment {
  const Experiment({
    required this.id,
    required this.key,
    required this.name,
    required this.kind,
    required this.status,
    required this.primaryMetric,
    required this.trafficPercent,
    required this.variants,
    required this.exposedTotal,
    this.description,
    this.hypothesis,
    this.startedAt,
    this.endedAt,
    this.winnerKey,
  });

  final String id;
  final String key;
  final String name;
  final String? description;
  final String? hypothesis;
  final String kind;
  final String status; // draft | running | paused | completed
  final String primaryMetric;
  final int trafficPercent;
  final List<ExperimentVariant> variants;
  final int exposedTotal;
  final String? startedAt;
  final String? endedAt;
  final String? winnerKey;

  factory Experiment.fromJson(Map<String, dynamic> json) {
    return Experiment(
      id: json['id'] as String,
      key: json['key'] as String,
      name: json['name'] as String,
      description: json['description'] as String?,
      hypothesis: json['hypothesis'] as String?,
      kind: json['kind'] as String,
      status: json['status'] as String? ?? 'draft',
      primaryMetric: json['primary_metric'] as String? ?? 'conversion',
      trafficPercent: _asInt(json['traffic_percent']),
      variants: (json['variants'] as List<dynamic>? ?? const [])
          .map((e) => ExperimentVariant.fromJson(e as Map<String, dynamic>))
          .toList(),
      exposedTotal: _asInt(json['exposed_total']),
      startedAt: json['started_at'] as String?,
      endedAt: json['ended_at'] as String?,
      winnerKey: json['winner_key'] as String?,
    );
  }
}

class ExperimentPage {
  const ExperimentPage({required this.items, required this.total, required this.page, required this.totalPages});

  final List<Experiment> items;
  final int total;
  final int page;
  final int totalPages;

  factory ExperimentPage.fromJson(Map<String, dynamic> json) {
    return ExperimentPage(
      items: (json['items'] as List<dynamic>? ?? const [])
          .map((e) => Experiment.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: _asInt(json['total']),
      page: (json['page'] as num?)?.toInt() ?? 1,
      totalPages: (json['total_pages'] as num?)?.toInt() ?? 1,
    );
  }
}

class ExperimentStatsData {
  const ExperimentStatsData({
    required this.total,
    required this.byStatus,
    required this.runningNames,
    required this.exposedCustomers,
    required this.completed30d,
  });

  final int total;
  final Map<String, int> byStatus;
  final List<String> runningNames;
  final int exposedCustomers;
  final int completed30d;

  factory ExperimentStatsData.fromJson(Map<String, dynamic> json) {
    final status = json['by_status'] as Map<String, dynamic>? ?? const {};
    return ExperimentStatsData(
      total: _asInt(json['total']),
      byStatus: status.map((key, value) => MapEntry(key, _asInt(value))),
      runningNames: (json['running'] as List<dynamic>? ?? const [])
          .map((e) => (e as Map<String, dynamic>)['name'] as String)
          .toList(),
      exposedCustomers: _asInt(json['exposed_customers']),
      completed30d: _asInt(json['completed_30d']),
    );
  }
}

class Comparison {
  const Comparison({
    required this.control,
    required this.variant,
    required this.diff,
    required this.pValue,
    required this.ciLow,
    required this.ciHigh,
    required this.significant,
    this.lift,
  });

  final double control;
  final double variant;
  final double diff;
  final double? lift;
  final double pValue;
  final double ciLow;
  final double ciHigh;
  final bool significant;

  static Comparison? fromJson(dynamic json) {
    if (json is! Map<String, dynamic>) return null;
    return Comparison(
      control: _asDouble(json['control']),
      variant: _asDouble(json['variant']),
      diff: _asDouble(json['diff']),
      lift: (json['lift'] as num?)?.toDouble(),
      pValue: _asDouble(json['p_value']),
      ciLow: _asDouble(json['ci_low']),
      ciHigh: _asDouble(json['ci_high']),
      significant: json['significant'] as bool? ?? false,
    );
  }
}

class VariantResult {
  const VariantResult({
    required this.key,
    required this.name,
    required this.isControl,
    required this.customers,
    required this.conversions,
    required this.clickers,
    required this.revenueTotal,
    required this.comparisons,
    this.conversionRate,
    this.clickRate,
    this.revenuePerCustomer,
  });

  final String key;
  final String name;
  final bool isControl;
  final int customers;
  final int conversions;
  final double? conversionRate;
  final int clickers;
  final double? clickRate;
  final double revenueTotal;
  final double? revenuePerCustomer;

  /// Comparison against the control per metric (conversion | click | revenue); empty for the control itself.
  final Map<String, Comparison?> comparisons;

  factory VariantResult.fromJson(Map<String, dynamic> json) {
    final comparisons = json['comparisons'] as Map<String, dynamic>? ?? const {};
    return VariantResult(
      key: json['key'] as String,
      name: json['name'] as String,
      isControl: json['is_control'] as bool? ?? false,
      customers: _asInt(json['customers']),
      conversions: _asInt(json['conversions']),
      conversionRate: (json['conversion_rate'] as num?)?.toDouble(),
      clickers: _asInt(json['clickers']),
      clickRate: (json['click_rate'] as num?)?.toDouble(),
      revenueTotal: _asDouble(json['revenue_total']),
      revenuePerCustomer: (json['revenue_per_customer'] as num?)?.toDouble(),
      comparisons: comparisons.map((key, value) => MapEntry(key, Comparison.fromJson(value))),
    );
  }
}

class Verdict {
  const Verdict({required this.status, required this.message, this.winnerKey});

  final String status; // collecting | winner | control_better | inconclusive
  final String? winnerKey;
  final String message;

  factory Verdict.fromJson(Map<String, dynamic> json) {
    return Verdict(
      status: json['status'] as String? ?? 'collecting',
      winnerKey: json['winner_key'] as String?,
      message: json['message'] as String? ?? '',
    );
  }
}

class ExperimentResults {
  const ExperimentResults({
    required this.primaryMetric,
    required this.variants,
    required this.verdict,
    required this.minPerVariant,
    required this.smallestVariant,
    this.neededPerVariant,
  });

  final String primaryMetric;
  final List<VariantResult> variants;
  final Verdict verdict;
  final int minPerVariant;
  final int smallestVariant;
  final int? neededPerVariant;

  factory ExperimentResults.fromJson(Map<String, dynamic> json) {
    final sample = json['sample'] as Map<String, dynamic>? ?? const {};
    return ExperimentResults(
      primaryMetric: json['primary_metric'] as String? ?? 'conversion',
      variants: (json['variants'] as List<dynamic>? ?? const [])
          .map((e) => VariantResult.fromJson(e as Map<String, dynamic>))
          .toList(),
      verdict: Verdict.fromJson(json['verdict'] as Map<String, dynamic>? ?? const {}),
      minPerVariant: _asInt(sample['min_per_variant']),
      smallestVariant: _asInt(sample['smallest_variant']),
      neededPerVariant: (sample['needed_per_variant_for_10pct_lift'] as num?)?.toInt(),
    );
  }
}

class AssignmentPreview {
  const AssignmentPreview({required this.inExperiment, required this.alreadyExposed, this.variant});

  final bool inExperiment;
  final String? variant;
  final bool alreadyExposed;

  factory AssignmentPreview.fromJson(Map<String, dynamic> json) {
    return AssignmentPreview(
      inExperiment: json['in_experiment'] as bool? ?? false,
      variant: json['variant'] as String?,
      alreadyExposed: json['already_exposed'] as bool? ?? false,
    );
  }
}

/// One variant in the create / edit form.
class VariantInput {
  const VariantInput({required this.name, this.key, this.weight = 1, this.strategy = 'hybrid', this.offerCodes});

  final String name;
  final String? key;
  final double weight;
  final String strategy; // recommendations experiments
  final List<String>? offerCodes; // offers experiments: null = all offers, [] = none (holdout)

  Map<String, dynamic> toJson(String kind) {
    final trimmedKey = key?.trim();
    return {
      if (trimmedKey != null && trimmedKey.isNotEmpty) 'key': trimmedKey,
      'name': name.trim(),
      'weight': weight,
      'config': kind == 'recommendations'
          ? {'strategy': strategy}
          : (offerCodes == null ? <String, dynamic>{} : {'offer_codes': offerCodes}),
    };
  }
}

class ExperimentInput {
  const ExperimentInput({
    required this.key,
    required this.name,
    required this.kind,
    required this.primaryMetric,
    required this.trafficPercent,
    required this.variants,
    this.description,
    this.hypothesis,
  });

  final String key;
  final String name;
  final String? description;
  final String? hypothesis;
  final String kind;
  final String primaryMetric;
  final int trafficPercent;
  final List<VariantInput> variants;

  Map<String, dynamic> toJson() {
    String? clean(String? value) {
      final trimmed = value?.trim();
      return (trimmed == null || trimmed.isEmpty) ? null : trimmed;
    }

    return {
      'key': key.trim().toLowerCase(),
      'name': name.trim(),
      'description': clean(description),
      'hypothesis': clean(hypothesis),
      'kind': kind,
      'primary_metric': primaryMetric,
      'traffic_percent': trafficPercent,
      'variants': variants.map((v) => v.toJson(kind)).toList(),
    };
  }
}

class ExperimentQuery {
  const ExperimentQuery({this.status, this.page = 1});

  final String? status;
  final int page;

  static const int pageSize = 10;

  ExperimentQuery copyWith({String? status, bool clearStatus = false, int? page}) {
    return ExperimentQuery(status: clearStatus ? null : (status ?? this.status), page: page ?? 1);
  }
}
