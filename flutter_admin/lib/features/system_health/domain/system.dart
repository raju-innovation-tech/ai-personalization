int _asInt(dynamic value) => (value as num?)?.toInt() ?? 0;

class TableCount {
  const TableCount({required this.name, required this.rows});

  final String name;
  final int rows;
}

class SystemStatus {
  const SystemStatus({
    required this.appName,
    required this.version,
    required this.environment,
    required this.startedAt,
    required this.uptimeSeconds,
    required this.dbOk,
    required this.dbSizeBytes,
    required this.tables,
    required this.redisOk,
    required this.profileRefreshMinutes,
    required this.snapshotTtlSeconds,
    required this.config,
    this.dbLatencyMs,
    this.dbVersion,
    this.migration,
    this.redisLatencyMs,
    this.redisVersion,
    this.redisMemoryBytes,
    this.redisError,
    this.profilesComputedAt,
    this.snapshotBuiltAt,
    this.snapshotProducts,
  });

  final String appName;
  final String version;
  final String environment;
  final String startedAt;
  final int uptimeSeconds;

  final bool dbOk;
  final double? dbLatencyMs;
  final String? dbVersion;
  final int dbSizeBytes;
  final String? migration;
  final List<TableCount> tables;

  final bool redisOk;
  final double? redisLatencyMs;
  final String? redisVersion;
  final int? redisMemoryBytes;
  final String? redisError;

  final int profileRefreshMinutes;
  final String? profilesComputedAt;
  final String? snapshotBuiltAt;
  final int? snapshotProducts;
  final int snapshotTtlSeconds;

  final Map<String, dynamic> config;

  factory SystemStatus.fromJson(Map<String, dynamic> json) {
    final app = json['app'] as Map<String, dynamic>? ?? const {};
    final db = json['database'] as Map<String, dynamic>? ?? const {};
    final redis = json['redis'] as Map<String, dynamic>? ?? const {};
    final jobs = json['jobs'] as Map<String, dynamic>? ?? const {};
    final reco = json['recommendations'] as Map<String, dynamic>? ?? const {};

    return SystemStatus(
      appName: app['name'] as String? ?? '',
      version: app['version'] as String? ?? '',
      environment: app['environment'] as String? ?? '',
      startedAt: app['started_at'] as String? ?? '',
      uptimeSeconds: _asInt(app['uptime_seconds']),
      dbOk: db['ok'] as bool? ?? false,
      dbLatencyMs: (db['latency_ms'] as num?)?.toDouble(),
      dbVersion: db['version'] as String?,
      dbSizeBytes: _asInt(db['size_bytes']),
      migration: db['migration'] as String?,
      tables: (db['tables'] as List<dynamic>? ?? const []).map((e) {
        final row = e as Map<String, dynamic>;
        return TableCount(name: row['name'] as String, rows: _asInt(row['rows']));
      }).toList(),
      redisOk: redis['ok'] as bool? ?? false,
      redisLatencyMs: (redis['latency_ms'] as num?)?.toDouble(),
      redisVersion: redis['version'] as String?,
      redisMemoryBytes: (redis['used_memory_bytes'] as num?)?.toInt(),
      redisError: redis['error'] as String?,
      profileRefreshMinutes: _asInt(jobs['profile_refresh_minutes']),
      profilesComputedAt: jobs['profiles_computed_at'] as String?,
      snapshotBuiltAt: reco['snapshot_built_at'] as String?,
      snapshotProducts: (reco['snapshot_products'] as num?)?.toInt(),
      snapshotTtlSeconds: _asInt(reco['ttl_seconds']),
      config: json['config'] as Map<String, dynamic>? ?? const {},
    );
  }
}

class AppAlert {
  const AppAlert({required this.id, required this.severity, required this.title, required this.message, this.link});

  final String id;
  final String severity; // critical | warning | info
  final String title;
  final String message;
  final String? link;

  factory AppAlert.fromJson(Map<String, dynamic> json) {
    return AppAlert(
      id: json['id'] as String,
      severity: json['severity'] as String? ?? 'info',
      title: json['title'] as String? ?? '',
      message: json['message'] as String? ?? '',
      link: json['link'] as String?,
    );
  }
}

class AlertsResult {
  const AlertsResult({required this.count, required this.needsAttention, required this.items});

  final int count;
  final int needsAttention;
  final List<AppAlert> items;

  factory AlertsResult.fromJson(Map<String, dynamic> json) {
    return AlertsResult(
      count: _asInt(json['count']),
      needsAttention: _asInt(json['needs_attention']),
      items: (json['items'] as List<dynamic>? ?? const [])
          .map((e) => AppAlert.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
