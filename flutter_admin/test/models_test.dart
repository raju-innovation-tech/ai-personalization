import 'package:flutter_test/flutter_test.dart';

import 'package:ai_personalization_admin/features/dashboard/domain/overview.dart';
import 'package:ai_personalization_admin/features/products/domain/product.dart';
import 'package:ai_personalization_admin/features/recommendations/domain/recommendation.dart';

void main() {
  test('Product.fromJson parses a full and a minimal payload', () {
    final full = Product.fromJson({
      'product_id': 'PROD_1',
      'name': 'Acme Laptop',
      'category': 'Laptops',
      'brand': 'Acme',
      'price': 59999,
      'rating': 4.5,
      'tags': ['trending'],
      'is_active': true,
      'in_stock': false,
    });
    expect(full.price, 59999.0);
    expect(full.tags, ['trending']);
    expect(full.inStock, isFalse);

    final minimal = Product.fromJson({'product_id': 'X', 'name': 'Bare'});
    expect(minimal.price, isNull);
    expect(minimal.tags, isEmpty);
    expect(minimal.inStock, isTrue);
  });

  test('ProductPage and ProductFilters parse envelopes', () {
    final page = ProductPage.fromJson({
      'items': [
        {'product_id': 'A', 'name': 'A'}
      ],
      'total': 21,
      'page': 2,
      'page_size': 20,
      'total_pages': 2,
    });
    expect(page.items.single.productId, 'A');
    expect(page.totalPages, 2);

    final filters = ProductFilters.fromJson({'categories': ['Laptops'], 'brands': ['Acme', 'Zeta']});
    expect(filters.brands.length, 2);
  });

  test('ProductQuery.copyWith resets to page 1 unless a page is given', () {
    const query = ProductQuery(page: 4, category: 'Laptops');
    expect(query.copyWith(search: 'nike').page, 1);
    expect(query.copyWith(page: 5).page, 5);
    expect(query.copyWith(clearCategory: true).category, isNull);
    expect(query.copyWith(sort: 'price').category, 'Laptops');
  });

  test('RecommendationResult.fromJson handles personalized flag and items', () {
    final result = RecommendationResult.fromJson({
      'algorithm': 'hybrid',
      'personalized': true,
      'items': [
        {
          'product_id': 'P1',
          'name': 'Thing',
          'score': 0.5,
          'reason': 'Because',
          'algorithm': 'content',
          'price': 10,
        }
      ],
    });
    expect(result.personalized, isTrue);
    expect(result.items.single.score, 0.5);
    expect(result.items.single.price, 10.0);
  });

  test('EngineStatus.fromJson parses per-algorithm usage', () {
    final status = EngineStatus.fromJson({
      'built_at': '2026-10-07T10:00:00+00:00',
      'products': 500,
      'customers_with_history': 1000,
      'interactions': 7588,
      'baskets': 630,
      'fbt_pairs': 46,
      'served_total': 7,
      'served_7d': 7,
      'lookback_days': 90,
      'served_by_algorithm': {
        'fbt': {'total': 3, 'last_7d': 2}
      },
    });
    expect(status.servedByAlgorithm['fbt']!.last7d, 2);
    expect(status.fbtPairs, 46);
  });

  test('DashboardOverview.fromJson tolerates a null CTR and fills charts', () {
    final overview = DashboardOverview.fromJson({
      'totals': {'customers': 1000, 'products': 500, 'active_products': 490, 'events': 11624},
      'recommendation_ctr_30d': {'impressions': 0, 'clicks': 0, 'ctr': null},
      'events_by_day': [
        {'date': '2026-10-07', 'count': 12}
      ],
      'events_by_type': [
        {'event_type': 'PURCHASE', 'count': 3}
      ],
      'top_categories': [
        {'category': 'Laptops', 'interactions': 9}
      ],
    });
    expect(overview.customers, 1000);
    expect(overview.ctr, isNull);
    expect(overview.eventsByDay.single.count, 12);
    expect(overview.topCategories.single.name, 'Laptops');
    expect(overview.recommendationsServed, 0); // missing -> 0
  });
}
