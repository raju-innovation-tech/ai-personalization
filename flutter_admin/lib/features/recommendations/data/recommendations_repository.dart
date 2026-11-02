import '../../../core/network/api_client.dart';
import '../domain/recommendation.dart';

class RecommendationsRepository {
  RecommendationsRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<RecommendationResult> _result(String path, Map<String, dynamic> params) async {
    final response = await _apiClient.get(path, queryParameters: params);
    return RecommendationResult.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<RecommendationResult> similar(String productId, {int limit = 6}) =>
      _result('/recommendations/similar/${Uri.encodeComponent(productId)}', {'limit': limit});

  Future<RecommendationResult> frequentlyBought(String productId, {int limit = 6}) =>
      _result('/recommendations/frequently-bought/${Uri.encodeComponent(productId)}', {'limit': limit});

  Future<RecommendationResult> forUser(String userId, {int limit = 10}) =>
      _result('/recommendations/user/${Uri.encodeComponent(userId)}', {'limit': limit});

  Future<RecommendationResult> popular({String? category, int limit = 10}) {
    final params = <String, dynamic>{'limit': limit};
    if (category != null && category.trim().isNotEmpty) params['category'] = category.trim();
    return _result('/recommendations/popular', params);
  }

  Future<EngineStatus> status() async {
    final response = await _apiClient.get('/recommendations/status');
    return EngineStatus.fromJson(response['data'] as Map<String, dynamic>);
  }

  /// Rebuilds the model snapshot on the server (admin only).
  Future<void> refresh() async {
    await _apiClient.post('/recommendations/refresh');
  }
}
