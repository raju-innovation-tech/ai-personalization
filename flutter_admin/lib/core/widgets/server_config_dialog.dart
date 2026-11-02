import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../constants/app_constants.dart';
import '../theme/app_colors.dart';
import '../../features/auth/presentation/providers/core_providers.dart';
import '../../features/dashboard/presentation/providers/dashboard_providers.dart';

void showServerConfigDialog(BuildContext context) {
  showDialog<void>(
    context: context,
    builder: (_) => const ServerConfigDialog(),
  );
}

class ServerConfigDialog extends ConsumerStatefulWidget {
  const ServerConfigDialog({super.key});

  @override
  ConsumerState<ServerConfigDialog> createState() => _ServerConfigDialogState();
}

class _ServerConfigDialogState extends ConsumerState<ServerConfigDialog> {
  late final TextEditingController _controller;
  bool _testing = false;
  bool? _testResult;
  String? _testMessage;

  @override
  void initState() {
    super.initState();
    final client = ref.read(apiClientProvider);
    _controller = TextEditingController(text: client.baseUrl);
    _testConnection(client.baseUrl);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _testConnection(String url) async {
    setState(() {
      _testing = true;
      _testResult = null;
      _testMessage = null;
    });

    final client = ref.read(apiClientProvider);
    final stopwatch = Stopwatch()..start();
    final ok = await client.pingServer(url);
    stopwatch.stop();

    if (!mounted) return;
    setState(() {
      _testing = false;
      _testResult = ok;
      _testMessage = ok
          ? 'Connected (${stopwatch.elapsedMilliseconds}ms)'
          : 'Could not reach server at this address';
    });
  }

  void _applyUrl(String url) {
    ref.read(apiClientProvider).updateBaseUrl(url);
    ref.invalidate(systemHealthProvider);
    ref.invalidate(dashboardOverviewProvider);
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Connected to: $url'),
        backgroundColor: AppColors.success,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: Padding(
          padding: const EdgeInsets.all(22),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: AppColors.primary.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(Icons.dns_rounded, color: AppColors.primary, size: 20),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      'Server Connection',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close_rounded, size: 20),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                'Select your development environment or enter the host address to connect to FastAPI backend.',
                style: TextStyle(
                  fontSize: 13,
                  color: isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight,
                ),
              ),
              const SizedBox(height: 16),
              // Preset chips
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  ActionChip(
                    avatar: const Icon(Icons.wifi_rounded, size: 16),
                    label: const Text('Wi-Fi (192.168.1.28)'),
                    onPressed: () {
                      _controller.text = AppConstants.lanApiBaseUrl;
                      _testConnection(AppConstants.lanApiBaseUrl);
                    },
                  ),
                  ActionChip(
                    avatar: const Icon(Icons.laptop_rounded, size: 16),
                    label: const Text('Localhost (PC)'),
                    onPressed: () {
                      _controller.text = AppConstants.defaultApiBaseUrl;
                      _testConnection(AppConstants.defaultApiBaseUrl);
                    },
                  ),
                  ActionChip(
                    avatar: const Icon(Icons.android_rounded, size: 16),
                    label: const Text('Emulator (10.0.2.2)'),
                    onPressed: () {
                      _controller.text = AppConstants.emulatorApiBaseUrl;
                      _testConnection(AppConstants.emulatorApiBaseUrl);
                    },
                  ),
                ],
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _controller,
                decoration: InputDecoration(
                  labelText: 'API Base URL',
                  hintText: 'http://192.168.1.28:8000/api/v1',
                  prefixIcon: const Icon(Icons.link_rounded, size: 20),
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.refresh_rounded, size: 20),
                    tooltip: 'Test this URL',
                    onPressed: () => _testConnection(_controller.text.trim()),
                  ),
                  isDense: true,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
              const SizedBox(height: 12),
              // Live status indicator
              if (_testing)
                const Row(
                  children: [
                    SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                    SizedBox(width: 8),
                    Text('Testing connection...', style: TextStyle(fontSize: 12)),
                  ],
                )
              else if (_testResult != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(
                    color: (_testResult! ? AppColors.success : AppColors.danger).withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: (_testResult! ? AppColors.success : AppColors.danger).withValues(alpha: 0.3),
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        _testResult! ? Icons.check_circle_rounded : Icons.error_outline_rounded,
                        color: _testResult! ? AppColors.success : AppColors.danger,
                        size: 16,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        _testMessage ?? '',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: _testResult! ? AppColors.success : AppColors.danger,
                        ),
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  const SizedBox(width: 10),
                  FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    ),
                    icon: const Icon(Icons.check_rounded, size: 18),
                    label: const Text('Save & Apply'),
                    onPressed: () => _applyUrl(_controller.text.trim()),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
