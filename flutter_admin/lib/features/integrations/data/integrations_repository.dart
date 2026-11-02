import '../../../core/network/api_client.dart';
import '../domain/integration_status.dart';

class IntegrationsRepository {
  IntegrationsRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<IntegrationStatus> fetchStatus() async {
    final response = await _apiClient.get('/integrations/status');
    return IntegrationStatus.fromJson(response['data'] as Map<String, dynamic>);
  }
}
