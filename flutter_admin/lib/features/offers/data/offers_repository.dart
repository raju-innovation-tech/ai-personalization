import '../../../core/network/api_client.dart';
import '../domain/offer.dart';

class OffersRepository {
  OffersRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<OfferPage> fetchPage(OfferQuery query) async {
    final params = <String, dynamic>{'page': query.page, 'page_size': OfferQuery.pageSize};
    if (query.status != null) params['status'] = query.status;
    if (query.search.trim().isNotEmpty) params['q'] = query.search.trim();
    final response = await _apiClient.get('/offers', queryParameters: params);
    return OfferPage.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<OfferTotals> fetchTotals() async {
    final response = await _apiClient.get('/offers/stats');
    return OfferTotals.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<Offer> create(OfferInput input) async {
    final response = await _apiClient.post('/offers', data: input.toJson());
    return Offer.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<Offer> update(String id, OfferInput input) async {
    final response = await _apiClient.put('/offers/$id', data: input.toJson());
    return Offer.fromJson(response['data'] as Map<String, dynamic>);
  }

  /// status: draft | active | paused | ended
  Future<Offer> setStatus(String id, String status) async {
    final response = await _apiClient.post('/offers/$id/status', data: {'status': status});
    return Offer.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<List<OfferSuggestion>> forUser(String userId, {String? category, double? cartValue, int limit = 5}) async {
    final params = <String, dynamic>{'limit': limit};
    if (category != null && category.trim().isNotEmpty) params['category'] = category.trim();
    if (cartValue != null) params['cart_value'] = cartValue;
    final response = await _apiClient.get('/offers/user/${Uri.encodeComponent(userId)}', queryParameters: params);
    final data = response['data'] as Map<String, dynamic>;
    return (data['items'] as List<dynamic>? ?? const [])
        .map((e) => OfferSuggestion.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}
