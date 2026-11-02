import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/api_client.dart';
import '../../../../core/storage/secure_token_storage.dart';
import '../../data/auth_repository.dart';
import 'auth_controller.dart';

final secureTokenStorageProvider = Provider<SecureTokenStorage>((ref) {
  return SecureTokenStorage();
});

final apiClientProvider = Provider<ApiClient>((ref) {
  final tokenStorage = ref.watch(secureTokenStorageProvider);
  return ApiClient(
    tokenStorage: tokenStorage,
    onUnauthorized: () {
      // Defer to next microtask so we don't mutate state during a build.
      Future.microtask(() => ref.read(authControllerProvider.notifier).forceLogout());
    },
  );
});

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepository(
    apiClient: ref.watch(apiClientProvider),
    tokenStorage: ref.watch(secureTokenStorageProvider),
  );
});
