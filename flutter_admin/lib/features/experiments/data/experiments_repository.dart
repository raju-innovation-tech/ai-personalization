import '../../../core/network/api_client.dart';
import '../domain/experiment.dart';

class ExperimentsRepository {
  ExperimentsRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<ExperimentPage> fetchPage(ExperimentQuery query) async {
    final params = <String, dynamic>{'page': query.page, 'page_size': ExperimentQuery.pageSize};
    if (query.status != null) params['status'] = query.status;
    final response = await _apiClient.get('/experiments', queryParameters: params);
    return ExperimentPage.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<ExperimentStatsData> fetchStats() async {
    final response = await _apiClient.get('/experiments/stats');
    return ExperimentStatsData.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<Experiment> fetchOne(String id) async {
    final response = await _apiClient.get('/experiments/$id');
    return Experiment.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<ExperimentResults> fetchResults(String id) async {
    final response = await _apiClient.get('/experiments/$id/results');
    return ExperimentResults.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<Experiment> create(ExperimentInput input) async {
    final response = await _apiClient.post('/experiments', data: input.toJson());
    return Experiment.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<Experiment> update(String id, ExperimentInput input) async {
    final response = await _apiClient.put('/experiments/$id', data: input.toJson());
    return Experiment.fromJson(response['data'] as Map<String, dynamic>);
  }

  /// status: running | paused | completed (winnerKey only when completing)
  Future<Experiment> setStatus(String id, String status, {String? winnerKey}) async {
    final response = await _apiClient.post(
      '/experiments/$id/status',
      data: {'status': status, if (winnerKey != null) 'winner_key': winnerKey},
    );
    return Experiment.fromJson(response['data'] as Map<String, dynamic>);
  }

  Future<void> deleteExperiment(String id) async {
    await _apiClient.delete('/experiments/$id');
  }

  Future<AssignmentPreview> previewAssignment(String id, String userId) async {
    final response = await _apiClient.get('/experiments/$id/assign/${Uri.encodeComponent(userId)}');
    return AssignmentPreview.fromJson(response['data'] as Map<String, dynamic>);
  }
}
