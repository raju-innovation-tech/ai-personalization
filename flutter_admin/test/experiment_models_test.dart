import 'package:flutter_test/flutter_test.dart';

import 'package:ai_personalization_admin/features/experiments/domain/experiment.dart';

void main() {
  final experimentJson = {
    'id': 'e1',
    'key': 'reco-hybrid-vs-content',
    'name': 'Hybrid vs content',
    'description': 'd',
    'hypothesis': 'h',
    'kind': 'recommendations',
    'status': 'running',
    'primary_metric': 'conversion',
    'traffic_percent': 60,
    'variants': [
      {'key': 'control', 'name': 'Hybrid', 'weight': 50, 'share': 0.5, 'config': {'strategy': 'hybrid'}, 'is_control': true, 'exposed': 295},
      {'key': 'content', 'name': 'Content', 'weight': 50, 'share': 0.5, 'config': {'strategy': 'content'}, 'is_control': false, 'exposed': 295},
    ],
    'exposed_total': 590,
    'started_at': '2026-10-01T00:00:00+00:00',
    'ended_at': null,
    'winner_key': null,
  };

  test('Experiment.fromJson parses variants, shares and exposure counts', () {
    final e = Experiment.fromJson(experimentJson);
    expect(e.key, 'reco-hybrid-vs-content');
    expect(e.trafficPercent, 60);
    expect(e.exposedTotal, 590);
    expect(e.variants.first.isControl, isTrue);
    expect(e.variants.last.share, 0.5);
    expect(e.endedAt, isNull);
    expect(e.variants.last.describe(e.kind), 'Content-based only');
  });

  test('ExperimentVariant.describe covers recommendation strategies and offer modes', () {
    ExperimentVariant variant(Map<String, dynamic> config) => ExperimentVariant(
          key: 'v',
          name: 'V',
          weight: 1,
          share: 0.5,
          config: config,
          isControl: false,
          exposed: 0,
        );
    expect(variant({}).describe('offers'), 'All offers (normal behaviour)');
    expect(variant({'offer_codes': []}).describe('offers'), 'No offers (holdout)');
    expect(variant({'offer_codes': ['VIP15', 'COMEBACK20']}).describe('offers'), 'Only VIP15, COMEBACK20');
    expect(variant({'strategy': 'popular'}).describe('recommendations'), contains('Popular'));
    expect(variant({}).describe('recommendations'), contains('Hybrid'));
  });

  test('ExperimentPage and stats parse', () {
    final page = ExperimentPage.fromJson({'items': [experimentJson], 'total': 3, 'page': 1, 'total_pages': 1});
    expect(page.items.single.name, 'Hybrid vs content');
    final stats = ExperimentStatsData.fromJson({
      'total': 3,
      'by_status': {'running': 1, 'draft': 1, 'completed': 1, 'paused': 0},
      'running': [
        {'id': 'e1', 'key': 'k', 'name': 'Hybrid vs content', 'kind': 'recommendations'}
      ],
      'exposed_customers': 990,
      'completed_30d': 1,
    });
    expect(stats.byStatus['running'], 1);
    expect(stats.runningNames, ['Hybrid vs content']);
    expect(stats.exposedCustomers, 990);
  });

  test('ExperimentResults.fromJson parses comparisons, verdict and sample info', () {
    final results = ExperimentResults.fromJson({
      'primary_metric': 'conversion',
      'variants': [
        {
          'key': 'control',
          'name': 'No offer',
          'is_control': true,
          'customers': 200,
          'conversions': 20,
          'conversion_rate': 0.1,
          'clickers': 0,
          'click_rate': 0.0,
          'revenue_total': 1000.0,
          'revenue_per_customer': 5.0,
          'comparisons': null,
        },
        {
          'key': 'comeback',
          'name': 'COMEBACK20',
          'is_control': false,
          'customers': 200,
          'conversions': 48,
          'conversion_rate': 0.24,
          'clickers': 0,
          'click_rate': 0.0,
          'revenue_total': 2400.0,
          'revenue_per_customer': 12.0,
          'comparisons': {
            'conversion': {'control': 0.1, 'variant': 0.24, 'diff': 0.14, 'lift': 1.4, 'p_value': 0.0004, 'ci_low': 0.06, 'ci_high': 0.22, 'significant': true},
            'click': null,
            'revenue': {'control': 5.0, 'variant': 12.0, 'diff': 7.0, 'lift': null, 'p_value': 0.2, 'ci_low': -3.0, 'ci_high': 17.0, 'significant': false},
          },
        },
      ],
      'verdict': {'status': 'winner', 'winner_key': 'comeback', 'message': 'COMEBACK20 beats the control.'},
      'sample': {'min_per_variant': 30, 'smallest_variant': 200, 'needed_per_variant_for_10pct_lift': 14751},
    });
    expect(results.variants.first.comparisons, isEmpty);
    final winner = results.variants.last;
    expect(winner.comparisons['conversion']!.significant, isTrue);
    expect(winner.comparisons['conversion']!.lift, 1.4);
    expect(winner.comparisons['click'], isNull);
    expect(winner.comparisons['revenue']!.lift, isNull);
    expect(results.verdict.status, 'winner');
    expect(results.verdict.winnerKey, 'comeback');
    expect(results.neededPerVariant, 14751);
  });

  test('AssignmentPreview.fromJson', () {
    final inside = AssignmentPreview.fromJson({'in_experiment': true, 'variant': 'control', 'already_exposed': true});
    expect(inside.variant, 'control');
    expect(inside.alreadyExposed, isTrue);
    expect(AssignmentPreview.fromJson({'in_experiment': false, 'variant': null, 'already_exposed': false}).inExperiment, isFalse);
  });

  test('ExperimentInput.toJson builds the API payload per kind', () {
    const reco = ExperimentInput(
      key: ' Reco-Test ',
      name: ' Reco ',
      kind: 'recommendations',
      primaryMetric: 'click',
      trafficPercent: 40,
      description: '  ',
      variants: [
        VariantInput(name: 'Control', key: 'control'),
        VariantInput(name: 'Popular', strategy: 'popular', weight: 2),
      ],
    );
    final json = reco.toJson();
    expect(json['key'], 'reco-test');
    expect(json['name'], 'Reco');
    expect(json['description'], isNull);
    expect(json['traffic_percent'], 40);
    final variants = json['variants'] as List<dynamic>;
    expect((variants.first as Map)['key'], 'control');
    expect((variants.last as Map).containsKey('key'), isFalse);
    expect(((variants.last as Map)['config'] as Map)['strategy'], 'popular');
    expect((variants.last as Map)['weight'], 2);

    const offers = ExperimentInput(
      key: 'offer-test',
      name: 'Offers',
      kind: 'offers',
      primaryMetric: 'conversion',
      trafficPercent: 100,
      variants: [
        VariantInput(name: 'All offers'),
        VariantInput(name: 'Holdout', offerCodes: []),
        VariantInput(name: 'Only VIP', offerCodes: ['VIP15']),
      ],
    );
    final offerVariants = offers.toJson()['variants'] as List<dynamic>;
    expect((offerVariants[0] as Map)['config'], isEmpty);
    expect(((offerVariants[1] as Map)['config'] as Map)['offer_codes'], isEmpty);
    expect(((offerVariants[2] as Map)['config'] as Map)['offer_codes'], ['VIP15']);
  });

  test('ExperimentQuery.copyWith resets the page and labels are readable', () {
    const query = ExperimentQuery(page: 3, status: 'running');
    expect(query.copyWith(status: 'draft').page, 1);
    expect(query.copyWith(page: 2).page, 2);
    expect(query.copyWith(clearStatus: true).status, isNull);
    expect(formatPValue(0.0004), 'p < 0.001');
    expect(formatPValue(0.0456), 'p = 0.046');
    expect(metricLabel('revenue'), 'Revenue per customer');
    expect(experimentKindLabel('offers'), 'Offers');
  });
}
