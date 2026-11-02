import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/experiments_repository.dart';
import '../../domain/experiment.dart';

final experimentsRepositoryProvider = Provider<ExperimentsRepository>((ref) {
  return ExperimentsRepository(apiClient: ref.watch(apiClientProvider));
});

final experimentQueryProvider = StateProvider<ExperimentQuery>((ref) => const ExperimentQuery());

final experimentsPageProvider = FutureProvider.autoDispose<ExperimentPage>((ref) async {
  final query = ref.watch(experimentQueryProvider);
  return ref.watch(experimentsRepositoryProvider).fetchPage(query);
});

final experimentStatsProvider = FutureProvider.autoDispose<ExperimentStatsData>((ref) async {
  return ref.watch(experimentsRepositoryProvider).fetchStats();
});

final experimentDetailProvider = FutureProvider.autoDispose.family<Experiment, String>((ref, id) async {
  return ref.watch(experimentsRepositoryProvider).fetchOne(id);
});

final experimentResultsProvider = FutureProvider.autoDispose.family<ExperimentResults, String>((ref, id) async {
  return ref.watch(experimentsRepositoryProvider).fetchResults(id);
});
