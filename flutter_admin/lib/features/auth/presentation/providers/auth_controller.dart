import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_failure.dart';
import 'auth_state.dart';
import 'core_providers.dart';

final authControllerProvider = StateNotifierProvider<AuthController, AuthState>((ref) {
  return AuthController(ref);
});

class AuthController extends StateNotifier<AuthState> {
  AuthController(this._ref) : super(const AuthInitial()) {
    _restoreSession();
  }

  final Ref _ref;

  Future<void> _restoreSession() async {
    try {
      final repository = _ref.read(authRepositoryProvider);
      final hasSession = await repository.hasStoredSession();
      if (!mounted) return;

      if (!hasSession) {
        state = const AuthUnauthenticated();
        return;
      }

      state = const AuthLoading();
      final user = await repository.fetchCurrentUser();
      if (!mounted) return;
      state = AuthAuthenticated(user);
    } catch (_) {
      // Storage unavailable, backend down, or token invalid -> show login.
      if (mounted) state = const AuthUnauthenticated();
    }
  }

  Future<void> login({required String email, required String password}) async {
    state = const AuthLoading();
    final repository = _ref.read(authRepositoryProvider);

    try {
      final user = await repository.login(email: email, password: password);
      if (!mounted) return;
      state = AuthAuthenticated(user);
    } on AppException catch (e) {
      if (mounted) state = AuthUnauthenticated(errorMessage: e.failure.message);
    } catch (_) {
      if (mounted) state = const AuthUnauthenticated(errorMessage: 'Login failed. Please try again.');
    }
  }

  Future<void> logout() async {
    final repository = _ref.read(authRepositoryProvider);
    await repository.logout();
    if (mounted) state = const AuthUnauthenticated();
  }

  Future<void> authenticateWithCurrentUser() async {
    state = const AuthLoading();
    try {
      final repository = _ref.read(authRepositoryProvider);
      final user = await repository.fetchCurrentUser();
      if (!mounted) return;
      state = AuthAuthenticated(user);
    } catch (_) {
      if (mounted) state = const AuthUnauthenticated();
    }
  }

  /// Called by the API client when a 401 cannot be recovered via refresh.
  void forceLogout() {
    if (state is AuthAuthenticated) {
      state = const AuthUnauthenticated(errorMessage: 'Your session has expired. Please log in again.');
    }
  }
}
