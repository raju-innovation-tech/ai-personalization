import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/core_providers.dart';
import '../../data/users_repository.dart';
import '../../domain/staff_user.dart';

final usersRepositoryProvider = Provider<UsersRepository>((ref) {
  return UsersRepository(apiClient: ref.watch(apiClientProvider));
});

final usersProvider = FutureProvider.autoDispose<List<StaffUser>>((ref) async {
  return ref.watch(usersRepositoryProvider).list();
});
