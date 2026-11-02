import '../../../core/network/api_client.dart';
import '../domain/report.dart';

class AnalyticsRepository {
  AnalyticsRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<AnalyticsReport> fetchReport(int days) async {
    final response = await _apiClient.get('/analytics/report', queryParameters: {'days': days});
    return AnalyticsReport.fromJson(response['data'] as Map<String, dynamic>);
  }
}
