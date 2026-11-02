import 'package:flutter_test/flutter_test.dart';

import 'package:ai_personalization_admin/features/customers/domain/customer.dart';
import 'package:ai_personalization_admin/features/segments/domain/segment.dart';

void main() {
  final customerJson = {
    'customer_id': 'USER_10005',
    'segment': {'key': 'champions', 'name': 'Champions', 'description': 'Best', 'action': 'Reward'},
    'first_seen_at': '2026-08-01T10:00:00+00:00',
    'last_seen_at': '2026-10-07T10:00:00+00:00',
    'stats': {
      'events': 40,
      'views': 20,
      'cart_adds': 6,
      'wishlist_adds': 2,
      'active_days': 9,
      'orders': 4,
      'items_purchased': 5,
      'returns': 0,
      'total_spend': 12345.5,
      'avg_order_value': 3086.38,
      'recency_days': 3,
    },
    'rfm': {'r': 5, 'f': 4, 'm': 5, 'code': '545'},
    'favorite_category': 'Laptops',
    'favorite_brand': 'Acme',
  };

  test('Customer.fromJson parses a scored customer', () {
    final customer = Customer.fromJson(customerJson);
    expect(customer.id, 'USER_10005');
    expect(customer.segment?.name, 'Champions');
    expect(customer.stats.totalSpend, 12345.5);
    expect(customer.stats.recencyDays, 3);
    expect(customer.rfm.isScored, isTrue);
    expect(customer.rfm.code, '545');
    expect(customer.favoriteCategory, 'Laptops');
  });

  test('Customer.fromJson tolerates an unscored customer', () {
    final customer = Customer.fromJson({
      'customer_id': 'NEW',
      'segment': null,
      'stats': {'total_spend': 0},
      'rfm': {'r': null, 'f': null, 'm': null, 'code': null},
    });
    expect(customer.segment, isNull);
    expect(customer.rfm.isScored, isFalse);
    expect(customer.stats.orders, 0);
    expect(customer.stats.avgOrderValue, isNull);
  });

  test('CustomerPage and TimelinePage parse envelopes', () {
    final page = CustomerPage.fromJson({
      'items': [customerJson],
      'total': 41,
      'page': 3,
      'page_size': 20,
      'total_pages': 3,
    });
    expect(page.items.single.id, 'USER_10005');
    expect(page.totalPages, 3);

    final timeline = TimelinePage.fromJson({
      'items': [
        {
          'event_type': 'PURCHASE',
          'product_id': 'P1',
          'product_name': 'Thing',
          'category': 'Laptops',
          'occurred_at': '2026-10-07T10:00:00+00:00',
          'platform': 'web',
        },
        {'event_type': 'PRODUCT_SEARCH', 'product_id': null, 'occurred_at': '2026-10-06T10:00:00+00:00'},
      ],
      'total': 2,
      'page': 1,
      'total_pages': 1,
    });
    expect(timeline.items.first.productName, 'Thing');
    expect(timeline.items.last.productId, isNull);
  });

  test('CustomerOverview.fromJson handles nulls and top spenders', () {
    final overview = CustomerOverview.fromJson({
      'totals': {
        'customers': 1000,
        'buyers': 569,
        'repeat_buyers': 184,
        'repeat_rate': 0.3234,
        'active_customers': 750,
        'new_customers': 307,
        'revenue': 65953957.1,
        'orders': 836,
        'avg_order_value': null,
      },
      'active_days': 30,
      'profiles_computed_at': null,
      'top_spenders': [
        {
          'customer_id': 'U1',
          'total_spend': 700000.5,
          'orders': 4,
          'segment': {'key': 'loyal', 'name': 'Loyal Customers'},
        }
      ],
    });
    expect(overview.repeatRate, 0.3234);
    expect(overview.avgOrderValue, isNull);
    expect(overview.profilesComputedAt, isNull);
    expect(overview.topSpenders.single.segment?.key, 'loyal');
  });

  test('CustomerQuery.copyWith resets to page 1 unless a page is given', () {
    const query = CustomerQuery(page: 4, segment: 'champions');
    expect(query.copyWith(search: 'u1').page, 1);
    expect(query.copyWith(page: 2).page, 2);
    expect(query.copyWith(clearSegment: true).segment, isNull);
    expect(query.copyWith(sort: 'spend').segment, 'champions');
  });

  test('SegmentOverview.fromJson parses segments and the RFM grid', () {
    final overview = SegmentOverview.fromJson({
      'total_customers': 10,
      'profiles_computed_at': '2026-10-08T04:00:00+00:00',
      'segments': [
        {
          'key': 'champions',
          'name': 'Champions',
          'description': 'd',
          'action': 'a',
          'customers': 3,
          'share': 0.3,
          'revenue': 1000.0,
          'revenue_share': 0.5,
          'avg_spend': 333.33,
          'avg_recency_days': 4.5,
          'avg_orders': 2.0,
        },
        {
          'key': 'lost',
          'name': 'Lost',
          'description': 'd',
          'action': 'a',
          'customers': 0,
          'share': 0,
          'revenue': 0,
          'revenue_share': 0,
          'avg_spend': null,
          'avg_recency_days': null,
          'avg_orders': null,
        },
      ],
      'rfm_grid': [
        {'r': 5, 'f': 4, 'count': 3}
      ],
    });
    expect(overview.segments.length, 2);
    expect(overview.segments.last.avgSpend, isNull);
    expect(overview.segments.first.share, 0.3);
    expect(overview.grid.single.count, 3);
  });
}
