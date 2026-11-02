import '../../../core/network/api_client.dart';
import '../domain/overview.dart';
import '../domain/system_health.dart';

class DashboardRepository {
  DashboardRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<SystemHealthStatus> fetchSystemHealth() async {
    final response = await _apiClient.get('/ready');
    return SystemHealthStatus.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<DashboardOverview> fetchOverview() async {
    final response = await _apiClient.get('/analytics/overview');
    return DashboardOverview.fromJson(response['data'] as Map<String, dynamic>);
  }
}
