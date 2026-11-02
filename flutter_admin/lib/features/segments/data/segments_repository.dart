import '../../../core/network/api_client.dart';
import '../domain/segment.dart';

class SegmentsRepository {
  SegmentsRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<SegmentOverview> fetchOverview() async {
    final response = await _apiClient.get('/segments');
    return SegmentOverview.fromJson(response['data'] as Map<String, dynamic>);
  }
}
