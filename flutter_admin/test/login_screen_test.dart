import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_personalization_admin/core/storage/secure_token_storage.dart';
import 'package:ai_personalization_admin/features/auth/presentation/providers/core_providers.dart';
import 'package:ai_personalization_admin/features/auth/presentation/screens/login_screen.dart';

/// In-memory stand-in: flutter_secure_storage is a platform plugin and is not
/// available inside `flutter test`.
class _FakeTokenStorage implements SecureTokenStorage {
  String? _access;
  String? _refresh;

  @override
  Future<void> saveTokens({required String accessToken, required String refreshToken}) async {
    _access = accessToken;
    _refresh = refreshToken;
  }

  @override
  Future<String?> getAccessToken() async => _access;

  @override
  Future<String?> getRefreshToken() async => _refresh;

  @override
  Future<void> clear() async {
    _access = null;
    _refresh = null;
  }
}

Widget _buildApp() {
  return ProviderScope(
    overrides: [secureTokenStorageProvider.overrideWithValue(_FakeTokenStorage())],
    child: const MaterialApp(home: LoginScreen()),
  );
}

void main() {
  testWidgets('LoginScreen renders email, password fields and sign-in button', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pump();

    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.byType(TextFormField), findsNWidgets(2));
    expect(find.widgetWithText(ElevatedButton, 'Sign In'), findsOneWidget);
  });

  testWidgets('LoginScreen shows validation errors on empty submit', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pump();

    await tester.tap(find.widgetWithText(ElevatedButton, 'Sign In'));
    await tester.pump();

    expect(find.text('Email is required'), findsOneWidget);
    expect(find.text('Password is required'), findsOneWidget);
  });
}
