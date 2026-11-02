import '../../../core/network/api_client.dart';
import '../domain/customer.dart';

class CustomersRepository {
  CustomersRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<CustomerPage> fetchPage(CustomerQuery query) async {
    final params = <String, dynamic>{
      'page': query.page,
      'page_size': CustomerQuery.pageSize,
      'sort': query.sort,
      'order': query.descending ? 'desc' : 'asc',
    };
    if (query.search.trim().isNotEmpty) params['q'] = query.search.trim();
    if (query.segment != null) params['segment'] = query.segment;

    final response = await _apiClient.get('/customers', queryParameters: params);
    return CustomerPage.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<Customer> fetchCustomer(String id) async {
    final response = await _apiClient.get('/customers/${Uri.encodeComponent(id)}');
    return Customer.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<TimelinePage> fetchTimeline(String id, {int page = 1, int pageSize = 15}) async {
    final response = await _apiClient.get(
      '/customers/${Uri.encodeComponent(id)}/timeline',
      queryParameters: {'page': page, 'page_size': pageSize},
    );
    return TimelinePage.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<CustomerOverview> fetchOverview() async {
    final response = await _apiClient.get('/customers/stats');
    return CustomerOverview.fromJson(response['data'] as Map<String, dynamic>);
  }

  /// Recomputes profiles, RFM scores and segments on the server (admin only).
  Future<void> recompute() async {
    await _apiClient.post('/customers/recompute');
  }
}
