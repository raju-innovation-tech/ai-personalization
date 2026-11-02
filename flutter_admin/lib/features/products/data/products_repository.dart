import '../../../core/network/api_client.dart';
import '../domain/product.dart';

class ProductsRepository {
  ProductsRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<ProductPage> fetchPage(ProductQuery query) async {
    final params = <String, dynamic>{
      'page': query.page,
      'page_size': ProductQuery.pageSize,
      'sort': query.sort,
      'order': query.descending ? 'desc' : 'asc',
    };
    if (query.search.trim().isNotEmpty) params['q'] = query.search.trim();
    if (query.category != null) params['category'] = query.category;

    final response = await _apiClient.get('/products', queryParameters: params);
    return ProductPage.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<ProductFilters> fetchFilters() async {
    final response = await _apiClient.get('/products/filters');
    return ProductFilters.fromJson(response['data'] as Map<String, dynamic>);
  }
}
