class SystemHealthStatus {
  const SystemHealthStatus({required this.status, required this.checks});

  final String status;
  final Map<String, String> checks;

  factory SystemHealthStatus.fromJson(Map<String, dynamic> json) {
    final checksJson = json['checks'] as Map<String, dynamic>? ?? {};
    return SystemHealthStatus(
      status: json['status'] as String,
      checks: checksJson.map((key, value) => MapEntry(key, value.toString())),
    );
  }
}
