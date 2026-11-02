import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/segments_repository.dart';
import '../../domain/segment.dart';

final segmentsRepositoryProvider = Provider<SegmentsRepository>((ref) {
  return SegmentsRepository(apiClient: ref.watch(apiClientProvider));
});

final segmentOverviewProvider = FutureProvider.autoDispose<SegmentOverview>((ref) async {
  return ref.watch(segmentsRepositoryProvider).fetchOverview();
});
