import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_personalization_admin/core/routing/nav_destinations.dart';
import 'package:ai_personalization_admin/core/theme/theme_controller.dart';
import 'package:ai_personalization_admin/core/utils/formatters.dart';
import 'package:ai_personalization_admin/features/analytics/domain/report.dart';
import 'package:ai_personalization_admin/features/auth/domain/admin_user.dart';
import 'package:ai_personalization_admin/features/integrations/domain/integration_status.dart';
import 'package:ai_personalization_admin/features/search/domain/search_results.dart';
import 'package:ai_personalization_admin/features/system_health/domain/system.dart';
import 'package:ai_personalization_admin/features/users/domain/staff_user.dart';

void main() {
  test('AnalyticsReport.fromJson parses KPIs, series, funnel and breakdowns', () {
    final report = AnalyticsReport.fromJson({
      'days': 7,
      'from': '2026-10-08',
      'to': '2026-10-14',
      'kpis': {
        'revenue': {'value': 2000.0, 'previous': 1000.0, 'change': 1.0},
        'orders': {'value': 2, 'previous': null, 'change': null},
      },
      'daily': [
        {
          'date': '2026-10-14',
          'events': 10,
          'active_customers': 3,
          'new_customers': 1,
          'orders': 2,
          'revenue': 2000.5,
          'rec_views': 4,
          'rec_clicks': 1,
          'recs_served': 6,
          'offer_impressions': 5,
          'offer_clicks': 2,
          'offer_redemptions': 1,
          'offer_discount': 100,
        }
      ],
      'funnel': [
        {'step': 'viewed', 'label': 'Viewed a product', 'customers': 3, 'rate_from_start': 1.0, 'rate_from_previous': 1.0},
        {'step': 'carted', 'label': 'Added to cart', 'customers': 2, 'rate_from_start': 0.6667, 'rate_from_previous': null},
      ],
      'top_products': [
        {'product_id': 'P1', 'name': 'Laptop', 'category': 'Laptops', 'units': 2, 'revenue': 2000, 'views': 5}
      ],
      'top_categories': [
        {'category': 'Laptops', 'revenue': 2000, 'share': 1.0}
      ],
      'platforms': [
        {'platform': 'web', 'events': 10, 'share': 1.0}
      ],
    });
    expect(report.kpi('revenue').change, 1.0);
    expect(report.kpi('orders').previous, isNull);
    expect(report.kpi('missing').value, 0); // unknown KPI -> zero, never a crash
    expect(report.daily.single.revenue, 2000.5);
    expect(report.daily.single.offerRedemptions, 1);
    expect(report.funnel.last.rateFromPrevious, isNull);
    expect(report.topProducts.single.units, 2);
    expect(report.topCategories.single.share, 1.0);
    expect(report.platforms.single.platform, 'web');
  });

  test('SystemStatus.fromJson and AlertsResult.fromJson', () {
    final status = SystemStatus.fromJson({
      'app': {'name': 'AI', 'version': '0.5.0', 'environment': 'development', 'started_at': '2026-10-14T10:00:00+00:00', 'uptime_seconds': 93784},
      'database': {
        'ok': true,
        'latency_ms': 1.5,
        'version': '16.4',
        'size_bytes': 28311552,
        'migration': 'e1f2',
        'tables': [
          {'name': 'users', 'rows': 3},
          {'name': 'user_events', 'rows': 16124},
        ],
      },
      'redis': {'ok': false, 'latency_ms': null, 'version': null, 'used_memory_bytes': null, 'error': 'refused'},
      'jobs': {'profile_refresh_minutes': 60, 'profiles_computed_at': null},
      'recommendations': {'snapshot_built_at': null, 'snapshot_products': null, 'ttl_seconds': 300},
      'config': {'reco_lookback_days': 90},
    });
    expect(status.version, '0.5.0');
    expect(status.tables.last.rows, 16124);
    expect(status.redisOk, isFalse);
    expect(status.redisError, 'refused');
    expect(status.profilesComputedAt, isNull);
    expect(status.config['reco_lookback_days'], 90);

    final alerts = AlertsResult.fromJson({
      'count': 2,
      'needs_attention': 1,
      'items': [
        {'id': 'events_stale', 'severity': 'warning', 'title': 'No events', 'message': 'm', 'link': '/integrations'},
        {'id': 'no_products', 'severity': 'info', 'title': 'No products', 'message': 'm', 'link': null},
      ],
    });
    expect(alerts.needsAttention, 1);
    expect(alerts.items.first.link, '/integrations');
    expect(alerts.items.last.link, isNull);
  });

  test('SearchResults.fromJson', () {
    final results = SearchResults.fromJson({
      'customers': [
        {'id': 'U1', 'segment': 'Champions'}
      ],
      'products': [
        {'id': 'P1', 'name': 'Laptop', 'category': null}
      ],
      'offers': [
        {'id': 'abc', 'code': 'VIP15', 'name': 'VIP', 'status': 'active'}
      ],
    });
    expect(results.isEmpty, isFalse);
    expect(results.customers.single.segment, 'Champions');
    expect(results.products.single.category, isNull);
    expect(results.offers.single.code, 'VIP15');
    expect(SearchResults.fromJson({}).isEmpty, isTrue);
  });

  test('IntegrationStatus.fromJson (admin view and non-admin view)', () {
    final json = {
      'score': 0.5556,
      'checklist': [
        {'key': 'catalog', 'title': 'Product catalog synced', 'status': 'ok', 'detail': '500 products'},
        {'key': 'events', 'title': 'Behaviour events arriving', 'status': 'todo', 'detail': 'No events yet'},
      ],
      'events': {'total': 10, 'last_24h': 4, 'last_7d': 9, 'last_event_at': null, 'event_types_30d': 6},
      'catalog': {'products': 500, 'active': 490, 'out_of_stock': 70, 'last_updated_at': null},
      'data_quality': {'unknown_product_rate': null, 'purchases_without_session_rate': 0.5, 'purchase_events_30d': 2},
      'profiles': {'last_computed_at': null},
      'recommendations': {'served_total': 7},
      'checkout': {'redemptions_total': 1},
      'accounts': [
        {'email': 'a@b.co', 'full_name': 'A', 'role': 'ADMIN', 'is_active': true}
      ],
    };
    final admin = IntegrationStatus.fromJson(json);
    expect(admin.doneCount, 1);
    expect(admin.unknownProductRate, isNull);
    expect(admin.purchasesWithoutSessionRate, 0.5);
    expect(admin.accounts!.single.role, 'ADMIN');
    expect(IntegrationStatus.fromJson({...json, 'accounts': null}).accounts, isNull);
  });

  test('StaffUser.fromJson maps roles and defaults unknown roles to viewer', () {
    final user = StaffUser.fromJson({
      'id': '1',
      'email': 'maya@example.com',
      'full_name': 'Maya',
      'role': 'MARKETING_MANAGER',
      'is_active': false,
    });
    expect(user.role, UserRole.marketingManager);
    expect(user.isActive, isFalse);
    expect(StaffUser.fromJson({'id': '2', 'email': 'x@y.z', 'role': 'WIZARD'}).role, UserRole.viewer);
  });

  test('formatters: bytes, duration and change', () {
    expect(formatBytes(null), '—');
    expect(formatBytes(512), '512 B');
    expect(formatBytes(28311552), '27.0 MB');
    expect(formatDuration(59), '59s');
    expect(formatDuration(3600), '1h 0m');
    expect(formatDuration(93784), '1d 2h 3m');
    expect(formatChange(null), '—');
    expect(formatChange(0.1234), '+12.3%');
    expect(formatChange(-0.05), '-5.0%');
    expect(formatChange(0), '0.0%');
  });

  test('theme mode survives a string round trip', () {
    for (final mode in ThemeMode.values) {
      expect(themeModeFromString(themeModeToString(mode)), mode);
    }
    expect(themeModeFromString(null), ThemeMode.system);
    expect(themeModeFromString('nonsense'), ThemeMode.system);
  });

  test('admin-only destinations are hidden from non-admins', () {
    final everyone = visibleDestinations(isAdmin: false).map((d) => d.path).toList();
    final admins = visibleDestinations(isAdmin: true).map((d) => d.path).toList();
    expect(everyone, isNot(contains('/users')));
    expect(everyone, isNot(contains('/system')));
    expect(admins, containsAll(['/users', '/system', '/analytics', '/integrations', '/offers']));
    expect(everyone, containsAll(['/dashboard', '/customers', '/analytics', '/integrations']));
  });
}
