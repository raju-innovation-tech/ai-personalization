import '../../../core/network/api_client.dart';
import '../domain/search_results.dart';

class SearchRepository {
  SearchRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<SearchResults> search(String query, {int limit = 5}) async {
    final response = await _apiClient.get('/search', queryParameters: {'q': query.trim(), 'limit': limit});
    return SearchResults.fromJson(response['data'] as Map<String, dynamic>);
  }
}
