import '../../../core/network/api_client.dart';
import '../domain/system.dart';

class SystemRepository {
  SystemRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<SystemStatus> fetchStatus() async {
    final response = await _apiClient.get('/system/status');
    return SystemStatus.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<AlertsResult> fetchAlerts() async {
    final response = await _apiClient.get('/system/alerts');
    return AlertsResult.fromJson(response['data'] as Map<String, dynamic>);
  }
}
