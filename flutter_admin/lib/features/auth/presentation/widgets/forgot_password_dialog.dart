import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_colors.dart';
import '../providers/auth_controller.dart';
import '../providers/core_providers.dart';

void showForgotPasswordDialog(
  BuildContext context, {
  String? initialEmail,
}) {
  showDialog<void>(
    context: context,
    barrierDismissible: true,
    builder: (_) => ForgotPasswordDialog(initialEmail: initialEmail),
  );
}

class ForgotPasswordDialog extends ConsumerStatefulWidget {
  const ForgotPasswordDialog({
    super.key,
    this.initialEmail,
  });

  final String? initialEmail;

  @override
  ConsumerState<ForgotPasswordDialog> createState() => _ForgotPasswordDialogState();
}

class _ForgotPasswordDialogState extends ConsumerState<ForgotPasswordDialog> {
  final _emailController = TextEditingController();
  final _newPasswordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();

  // 6 separate controllers and focus nodes for 6-digit PIN input
  final List<TextEditingController> _pinControllers = List.generate(6, (_) => TextEditingController());
  final List<FocusNode> _pinFocusNodes = List.generate(6, (_) => FocusNode());

  final _passwordFormKey = GlobalKey<FormState>();

  int _step = 1; // 1: Email, 2: 6-digit OTP Verification, 3: New Password
  bool _isLoading = false;
  String? _errorMessage;

  bool _obscureNewPassword = true;
  bool _obscureConfirmPassword = true;

  // Resend OTP 60-second countdown timer
  Timer? _resendTimer;
  int _resendCountdown = 60;
  bool _canResend = false;

  @override
  void initState() {
    super.initState();
    if (widget.initialEmail != null && widget.initialEmail!.trim().isNotEmpty) {
      _emailController.text = widget.initialEmail!.trim();
    }
  }

  @override
  void dispose() {
    _resendTimer?.cancel();
    _emailController.dispose();
    _newPasswordController.dispose();
    _confirmPasswordController.dispose();
    for (final c in _pinControllers) {
      c.dispose();
    }
    for (final f in _pinFocusNodes) {
      f.dispose();
    }
    super.dispose();
  }

  void _startResendTimer() {
    _resendTimer?.cancel();
    setState(() {
      _resendCountdown = 60;
      _canResend = false;
    });

    _resendTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      if (_resendCountdown <= 1) {
        timer.cancel();
        setState(() {
          _resendCountdown = 0;
          _canResend = true;
        });
      } else {
        setState(() {
          _resendCountdown--;
        });
      }
    });
  }

  String _getOtpCode() {
    return _pinControllers.map((c) => c.text.trim()).join();
  }

  void _clearOtpFields() {
    for (final c in _pinControllers) {
      c.clear();
    }
    if (_pinFocusNodes.isNotEmpty) {
      _pinFocusNodes[0].requestFocus();
    }
  }

  String _maskEmail(String email) {
    try {
      final parts = email.split('@');
      if (parts.length != 2) return email;
      final user = parts[0];
      final domain = parts[1];
      if (user.length <= 2) return '${user[0]}***@$domain';
      return '${user.substring(0, 2)}***${user[user.length - 1]}@$domain';
    } catch (_) {
      return email;
    }
  }

  Future<void> _requestOtp() async {
    final email = _emailController.text.trim();
    if (email.isEmpty || !email.contains('@')) {
      setState(() => _errorMessage = 'Please enter a valid email address.');
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final repo = ref.read(authRepositoryProvider);
      await repo.requestPasswordReset(email);

      if (!mounted) return;

      setState(() {
        _isLoading = false;
        _step = 2;
      });
      _clearOtpFields();
      _startResendTimer();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _errorMessage = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  Future<void> _resendOtp() async {
    if (!_canResend || _isLoading) return;
    final email = _emailController.text.trim();

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final repo = ref.read(authRepositoryProvider);
      await repo.requestPasswordReset(email);

      if (!mounted) return;

      setState(() {
        _isLoading = false;
      });
      _clearOtpFields();
      _startResendTimer();

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('A new 6-digit verification code has been dispatched to your email.'),
          backgroundColor: AppColors.success,
          behavior: SnackBarBehavior.floating,
          duration: Duration(seconds: 3),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _errorMessage = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  void _proceedToPasswordStep() {
    final code = _getOtpCode();
    if (code.length != 6) {
      setState(() => _errorMessage = 'Please enter the complete 6-digit verification code.');
      return;
    }

    setState(() {
      _errorMessage = null;
      _step = 3;
    });
  }

  Future<void> _submitReset() async {
    if (!_passwordFormKey.currentState!.validate()) return;

    final email = _emailController.text.trim();
    final code = _getOtpCode();
    final newPassword = _newPasswordController.text;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final repo = ref.read(authRepositoryProvider);
      await repo.resetPassword(
        email: email,
        code: code,
        newPassword: newPassword,
      );

      if (!mounted) return;

      // Close dialog
      Navigator.of(context).pop();

      // Show floating success message
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Row(
            children: [
              Icon(Icons.check_circle_rounded, color: Colors.white, size: 20),
              SizedBox(width: 10),
              Expanded(
                child: Text('Password reset successfully! Logged in with valid session.'),
              ),
            ],
          ),
          backgroundColor: AppColors.success,
          behavior: SnackBarBehavior.floating,
          duration: Duration(seconds: 4),
        ),
      );

      // Authenticate session directly into dashboard
      ref.read(authControllerProvider.notifier).authenticateWithCurrentUser();
    } catch (e) {
      if (!mounted) return;
      final errorMsg = e.toString().replaceFirst('Exception: ', '');
      setState(() {
        _isLoading = false;
        _errorMessage = errorMsg;
      });

      // If maximum attempts exceeded or code expired, switch back to OTP step
      if (errorMsg.contains('attempt') || errorMsg.contains('expired') || errorMsg.contains('code')) {
        setState(() => _step = 2);
        _clearOtpFields();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      backgroundColor: isDark ? AppColors.cardDark : Colors.white,
      elevation: 12,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 26, vertical: 28),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Top Header Row
                Row(
                  children: [
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          colors: [Color(0xFF7C3AED), Color(0xFF4F46E5)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        borderRadius: BorderRadius.circular(14),
                        boxShadow: [
                          BoxShadow(
                            color: const Color(0xFF7C3AED).withValues(alpha: 0.35),
                            blurRadius: 10,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: const Icon(Icons.lock_reset_rounded, color: Colors.white, size: 24),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _step == 1
                                ? 'Forgot Password'
                                : _step == 2
                                    ? 'Verify OTP'
                                    : 'Create New Password',
                            style: const TextStyle(fontSize: 18.5, fontWeight: FontWeight.w800, letterSpacing: -0.3),
                          ),
                          Text(
                            _step == 1
                                ? 'Step 1 of 3: Enter email'
                                : _step == 2
                                    ? 'Step 2 of 3: 6-Digit Code'
                                    : 'Step 3 of 3: Update credentials',
                            style: TextStyle(
                              fontSize: 12,
                              color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close_rounded, size: 20),
                      style: IconButton.styleFrom(
                        backgroundColor: isDark ? AppColors.backgroundDark : const Color(0xFFF1F5F9),
                      ),
                      onPressed: () => Navigator.of(context).pop(),
                    ),
                  ],
                ),
                const SizedBox(height: 18),

                // Error Banner
                if (_errorMessage != null) ...[
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppColors.danger.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppColors.danger.withValues(alpha: 0.3)),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(Icons.error_outline_rounded, color: AppColors.danger, size: 18),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            _errorMessage!,
                            style: const TextStyle(color: AppColors.danger, fontSize: 13, fontWeight: FontWeight.w500),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                ],

                // Step Body
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 250),
                  child: _step == 1
                      ? _buildStepEmail(isDark)
                      : _step == 2
                          ? _buildStepOtp(isDark)
                          : _buildStepNewPassword(isDark),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // ───────────────────────────────────────────────────────────────────────────
  // STEP 1: Enter Registered Email
  // ───────────────────────────────────────────────────────────────────────────
  Widget _buildStepEmail(bool isDark) {
    return Column(
      key: const ValueKey(1),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Enter your registered staff/admin email address. A secure 6-digit verification code will be sent to your inbox in real time.',
          style: TextStyle(
            fontSize: 13.5,
            color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
            height: 1.45,
          ),
        ),
        const SizedBox(height: 20),
        TextField(
          controller: _emailController,
          keyboardType: TextInputType.emailAddress,
          textInputAction: TextInputAction.done,
          enabled: !_isLoading,
          onSubmitted: (_) => _requestOtp(),
          decoration: InputDecoration(
            labelText: 'Registered Email Address',
            hintText: 'admin@example.com',
            prefixIcon: const Icon(Icons.email_outlined, size: 20),
            filled: true,
            fillColor: isDark ? AppColors.backgroundDark : const Color(0xFFF8FAFC),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
          ),
        ),
        const SizedBox(height: 24),
        ElevatedButton(
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF7C3AED),
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 16),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            elevation: 0,
          ),
          onPressed: _isLoading ? null : _requestOtp,
          child: _isLoading
              ? const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2.2, color: Colors.white),
                )
              : const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text('Send Real-Time OTP', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14.5)),
                    SizedBox(width: 8),
                    Icon(Icons.arrow_forward_rounded, size: 18),
                  ],
                ),
        ),
      ],
    );
  }

  // ───────────────────────────────────────────────────────────────────────────
  // STEP 2: Modern 6-Box Digit OTP Input & 60s Resend Countdown
  // ───────────────────────────────────────────────────────────────────────────
  Widget _buildStepOtp(bool isDark) {
    final emailMasked = _maskEmail(_emailController.text.trim());

    return Column(
      key: const ValueKey(2),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: const Color(0xFF7C3AED).withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFF7C3AED).withValues(alpha: 0.2)),
          ),
          child: Row(
            children: [
              const Icon(Icons.mark_email_read_rounded, color: Color(0xFF7C3AED), size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Verification code dispatched', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700)),
                    Text(
                      'Sent to $emailMasked',
                      style: TextStyle(fontSize: 12, color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight),
                    ),
                  ],
                ),
              ),
              TextButton(
                onPressed: _isLoading ? null : () => setState(() => _step = 1),
                child: const Text('Change', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),

        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              'Enter 6-digit code',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: isDark ? Colors.white70 : AppColors.textPrimaryLight,
              ),
            ),
            Row(
              children: [
                const Icon(Icons.timer_outlined, size: 14, color: AppColors.warning),
                const SizedBox(width: 4),
                const Text('Expires in 5m', style: TextStyle(fontSize: 11.5, color: AppColors.warning, fontWeight: FontWeight.w600)),
              ],
            ),
          ],
        ),
        const SizedBox(height: 12),

        // 6 Segmented PIN boxes
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: List.generate(6, (index) => _buildOtpBox(index, isDark)),
        ),
        const SizedBox(height: 20),

        // 60-Second Cooldown & Resend button
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              'Didn\'t receive code?',
              style: TextStyle(fontSize: 12.5, color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight),
            ),
            _canResend
                ? TextButton.icon(
                    style: TextButton.styleFrom(
                      foregroundColor: const Color(0xFF7C3AED),
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    ),
                    onPressed: _isLoading ? null : _resendOtp,
                    icon: const Icon(Icons.refresh_rounded, size: 16),
                    label: const Text('Resend OTP', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
                  )
                : Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: isDark ? AppColors.backgroundDark : const Color(0xFFF1F5F9),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.access_time_rounded, size: 14, color: Color(0xFF64748B)),
                        const SizedBox(width: 5),
                        Text(
                          'Resend in 00:${_resendCountdown.toString().padLeft(2, '0')}',
                          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF64748B)),
                        ),
                      ],
                    ),
                  ),
          ],
        ),
        const SizedBox(height: 24),

        ElevatedButton(
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF7C3AED),
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 16),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            elevation: 0,
          ),
          onPressed: _isLoading ? null : _proceedToPasswordStep,
          child: const Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text('Verify Code & Continue', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14.5)),
              SizedBox(width: 8),
              Icon(Icons.arrow_forward_rounded, size: 18),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildOtpBox(int index, bool isDark) {
    return SizedBox(
      width: 48,
      height: 56,
      child: TextFormField(
        controller: _pinControllers[index],
        focusNode: _pinFocusNodes[index],
        keyboardType: TextInputType.number,
        textAlign: TextAlign.center,
        style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: Color(0xFF7C3AED)),
        inputFormatters: [
          LengthLimitingTextInputFormatter(1),
          FilteringTextInputFormatter.digitsOnly,
        ],
        decoration: InputDecoration(
          counterText: '',
          contentPadding: EdgeInsets.zero,
          filled: true,
          fillColor: isDark ? AppColors.backgroundDark : const Color(0xFFF8FAFC),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(
              color: isDark ? AppColors.borderDark : const Color(0xFFCBD5E1),
              width: 1.5,
            ),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(
              color: Color(0xFF7C3AED),
              width: 2.2,
            ),
          ),
        ),
        onChanged: (value) {
          if (value.isNotEmpty) {
            if (index < 5) {
              _pinFocusNodes[index + 1].requestFocus();
            } else {
              _pinFocusNodes[index].unfocus();
              _proceedToPasswordStep();
            }
          } else if (value.isEmpty && index > 0) {
            _pinFocusNodes[index - 1].requestFocus();
          }
        },
      ),
    );
  }

  // ───────────────────────────────────────────────────────────────────────────
  // STEP 3: Set New Password & Auto-Authenticate Session
  // ───────────────────────────────────────────────────────────────────────────
  Widget _buildStepNewPassword(bool isDark) {
    return Form(
      key: _passwordFormKey,
      child: Column(
        key: const ValueKey(3),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Create a strong, secure password for your account.',
            style: TextStyle(
              fontSize: 13.5,
              color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
              height: 1.45,
            ),
          ),
          const SizedBox(height: 18),

          TextFormField(
            controller: _newPasswordController,
            obscureText: _obscureNewPassword,
            textInputAction: TextInputAction.next,
            enabled: !_isLoading,
            decoration: InputDecoration(
              labelText: 'New Password',
              hintText: 'Minimum 6 characters',
              prefixIcon: const Icon(Icons.lock_outline_rounded, size: 20),
              suffixIcon: IconButton(
                icon: Icon(
                  _obscureNewPassword ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                  size: 20,
                ),
                onPressed: () => setState(() => _obscureNewPassword = !_obscureNewPassword),
              ),
              filled: true,
              fillColor: isDark ? AppColors.backgroundDark : const Color(0xFFF8FAFC),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
            ),
            validator: (val) {
              if (val == null || val.length < 6) {
                return 'Password must be at least 6 characters';
              }
              return null;
            },
          ),
          const SizedBox(height: 14),

          TextFormField(
            controller: _confirmPasswordController,
            obscureText: _obscureConfirmPassword,
            textInputAction: TextInputAction.done,
            enabled: !_isLoading,
            onFieldSubmitted: (_) => _submitReset(),
            decoration: InputDecoration(
              labelText: 'Confirm New Password',
              prefixIcon: const Icon(Icons.lock_outline_rounded, size: 20),
              suffixIcon: IconButton(
                icon: Icon(
                  _obscureConfirmPassword ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                  size: 20,
                ),
                onPressed: () => setState(() => _obscureConfirmPassword = !_obscureConfirmPassword),
              ),
              filled: true,
              fillColor: isDark ? AppColors.backgroundDark : const Color(0xFFF8FAFC),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
            ),
            validator: (val) {
              if (val != _newPasswordController.text) {
                return 'Passwords do not match';
              }
              return null;
            },
          ),
          const SizedBox(height: 24),

          Row(
            children: [
              OutlinedButton(
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                ),
                onPressed: _isLoading ? null : () => setState(() => _step = 2),
                child: const Icon(Icons.arrow_back_rounded, size: 18),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF7C3AED),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    elevation: 0,
                  ),
                  onPressed: _isLoading ? null : _submitReset,
                  child: _isLoading
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(strokeWidth: 2.2, color: Colors.white),
                        )
                      : const Text('Update Password & Sign In', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14.5)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
