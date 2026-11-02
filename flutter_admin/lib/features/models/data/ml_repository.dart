import '../../../core/network/api_client.dart';
import '../domain/ml_models.dart';

class MlRepository {
  MlRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<List<MlModelInfo>> fetchModels() async {
    final response = await _apiClient.get('/ml/models');
    final models = response['data']['models'] as List<dynamic>? ?? [];
    return models
        .map((e) => MlModelInfo.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Map<String, dynamic>> rebuild() async {
    return await _apiClient.post('/ml/rebuild');
  }

  Future<CustomerMlProfile?> fetchCustomerProfile(String userId) async {
    try {
      final response = await _apiClient.get('/ml/customers/$userId');
      return CustomerMlProfile.fromJson(response['data'] as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  Future<List<TopRiskCustomer>> fetchTopChurnRisks({
    int limit = 20,
    double minScore = 0.5,
  }) async {
    final response = await _apiClient.get(
      '/ml/top/churn',
      queryParameters: {'limit': limit, 'min_score': minScore},
    );
    final customers = response['data']['customers'] as List<dynamic>? ?? [];
    return customers
        .map((e) => TopRiskCustomer.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<TopRiskCustomer>> fetchTopPurchaseProbability({
    int limit = 20,
    double minScore = 0.5,
  }) async {
    final response = await _apiClient.get(
      '/ml/top/purchase',
      queryParameters: {'limit': limit, 'min_score': minScore},
    );
    final customers = response['data']['customers'] as List<dynamic>? ?? [];
    return customers
        .map((e) => TopRiskCustomer.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<ScoreDistribution> fetchDistribution(String model) async {
    final response = await _apiClient.get('/ml/distribution/$model');
    return ScoreDistribution.fromJson(response['data'] as Map<String, dynamic>);
  }
}
