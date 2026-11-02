import 'package:flutter_test/flutter_test.dart';

import 'package:ai_personalization_admin/features/dashboard/domain/overview.dart';
import 'package:ai_personalization_admin/features/offers/domain/offer.dart';

void main() {
  final offerJson = {
    'id': '7d1c0c52-1b0f-4e2d-9d57-2a5b8f0b9a11',
    'code': 'COMEBACK20',
    'name': 'We miss you - 20% off',
    'description': 'Win-back campaign',
    'offer_type': 'percent_off',
    'value': 20,
    'max_discount': 3000,
    'min_order_value': null,
    'max_redemptions': 200,
    'max_per_customer': 1,
    'status': 'active',
    'effective_status': 'expired',
    'starts_at': '2026-08-01T00:00:00+00:00',
    'ends_at': '2026-10-01T00:00:00+00:00',
    'target_segments': ['at_risk', 'cant_lose'],
    'target_categories': [],
    'priority': 90,
    'stats': {
      'impressions': 75,
      'clicks': 29,
      'redemptions': 11,
      'ctr': 0.3867,
      'redemption_rate': 0.1467,
      'discount_given': 20388.77,
      'revenue': 246421.86,
      'remaining': 189,
    },
  };

  test('Offer.fromJson parses a full offer and keeps stored vs effective status', () {
    final offer = Offer.fromJson(offerJson);
    expect(offer.code, 'COMEBACK20');
    expect(offer.status, 'active');
    expect(offer.effectiveStatus, 'expired');
    expect(offer.targetSegments, ['at_risk', 'cant_lose']);
    expect(offer.maxRedemptions, 200);
    expect(offer.minOrderValue, isNull);
    expect(offer.stats.redemptions, 11);
    expect(offer.stats.remaining, 189);
    expect(offer.headline, contains('20% off'));
  });

  test('Offer.fromJson tolerates a minimal payload', () {
    final offer = Offer.fromJson({
      'id': 'x',
      'code': 'MIN',
      'name': 'Minimal',
      'offer_type': 'free_shipping',
      'value': 0,
      'stats': {'ctr': null},
    });
    expect(offer.status, 'draft');
    expect(offer.effectiveStatus, 'draft');
    expect(offer.maxPerCustomer, 1);
    expect(offer.stats.impressions, 0);
    expect(offer.stats.ctr, isNull);
    expect(offer.headline, 'Free shipping');
  });

  test('offerHeadline formats each offer type', () {
    expect(offerHeadline(type: 'percent_off', value: 10, maxDiscount: null), '10% off');
    expect(offerHeadline(type: 'percent_off', value: 12.5, maxDiscount: null), '12.5% off');
    expect(offerHeadline(type: 'percent_off', value: 15, maxDiscount: 500), contains('max'));
    expect(offerHeadline(type: 'fixed_off', value: 500, maxDiscount: null), contains('off'));
    expect(offerHeadline(type: 'free_shipping', value: 0, maxDiscount: null), 'Free shipping');
    expect(offerTypeLabel('fixed_off'), 'Fixed amount off');
  });

  test('OfferPage, OfferTotals and OfferSuggestion parse server envelopes', () {
    final page = OfferPage.fromJson({
      'items': [offerJson],
      'total': 11,
      'page': 2,
      'page_size': 10,
      'total_pages': 2,
    });
    expect(page.items.single.code, 'COMEBACK20');
    expect(page.totalPages, 2);

    final totals = OfferTotals.fromJson({
      'offers': 10,
      'by_status': {'draft': 1, 'active': 7, 'paused': 1, 'ended': 1},
      'active_now': 6,
      'all_time': {
        'impressions': 1650,
        'clicks': 383,
        'redemptions': 100,
        'discount_given': 203887.71,
        'revenue': 2464218.63,
        'ctr': 0.2321,
        'redemption_rate': 0.0606,
      },
      'last_30d': {'redemptions': 62},
    });
    expect(totals.activeNow, 6);
    expect(totals.byStatus['active'], 7);
    expect(totals.redemptions30d, 62);
    expect(totals.ctr, 0.2321);

    final suggestion = OfferSuggestion.fromJson({
      'id': 'a',
      'code': 'VIP15',
      'name': 'VIP',
      'offer_type': 'percent_off',
      'value': 15,
      'max_discount': 5000,
      'score': 0.6017,
      'reason': 'Made for Champions',
      'discount_preview': 5000,
      'free_shipping': false,
    });
    expect(suggestion.reason, 'Made for Champions');
    expect(suggestion.discountPreview, 5000.0);
    expect(suggestion.freeShipping, isFalse);
  });

  test('OfferInput.toJson sends UTC dates, upper-case codes and ignores value for free shipping', () {
    final input = OfferInput(
      code: ' welcome10 ',
      name: ' Welcome ',
      description: '   ',
      offerType: 'free_shipping',
      value: 99,
      maxPerCustomer: 2,
      priority: 70,
      startsAt: DateTime.utc(2026, 10, 1),
      targetSegments: const ['new_customer'],
    );
    final json = input.toJson();
    expect(json['code'], 'WELCOME10');
    expect(json['name'], 'Welcome');
    expect(json['description'], isNull);
    expect(json['value'], 0);
    expect(json['starts_at'], '2026-10-01T00:00:00.000Z');
    expect(json['ends_at'], isNull);
    expect(json['target_segments'], ['new_customer']);
    expect(json['max_per_customer'], 2);
  });

  test('OfferQuery.copyWith resets to page 1 unless a page is given', () {
    const query = OfferQuery(page: 3, status: 'active');
    expect(query.copyWith(search: 'vip').page, 1);
    expect(query.copyWith(page: 2).page, 2);
    expect(query.copyWith(clearStatus: true).status, isNull);
    expect(query.copyWith(search: 'x').status, 'active');
  });

  test('DashboardOverview parses the offers block and defaults it to zero', () {
    final withOffers = DashboardOverview.fromJson({
      'totals': {'customers': 1},
      'offers': {'active': 6, 'impressions': 1650, 'clicks': 383, 'redemptions': 100, 'discount_given': 203887.71},
    });
    expect(withOffers.offersActive, 6);
    expect(withOffers.offersImpressions, 1650);
    expect(withOffers.offersDiscountGiven, 203887.71);

    final without = DashboardOverview.fromJson({'totals': {}});
    expect(without.offersActive, 0);
    expect(without.offersRedemptions, 0);
  });
}
