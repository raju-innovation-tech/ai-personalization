import 'package:intl/intl.dart';

String formatCount(int value) => NumberFormat.decimalPattern('en_IN').format(value);

String formatPrice(double? value) {
  if (value == null) return '—';
  return NumberFormat.currency(locale: 'en_IN', symbol: '₹', decimalDigits: 0).format(value);
}

/// 0.2477 -> "24.8%"; null -> "—"
String formatPercent(double? ratio) {
  if (ratio == null) return '—';
  return '${(ratio * 100).toStringAsFixed(1)}%';
}

/// "PRODUCT_VIEW" -> "Product view"
String humanize(String raw) {
  final text = raw.toLowerCase().replaceAll('_', ' ');
  if (text.isEmpty) return text;
  return text[0].toUpperCase() + text.substring(1);
}

String formatTimestamp(String iso) {
  final parsed = DateTime.tryParse(iso);
  if (parsed == null) return iso;
  return DateFormat('d MMM y, HH:mm').format(parsed.toLocal());
}

/// 1234567 -> "₹12.3L" style compact money for KPI tiles.
String formatCompactPrice(double? value) {
  if (value == null) return '—';
  return NumberFormat.compactCurrency(locale: 'en_IN', symbol: '₹', decimalDigits: 1).format(value);
}

/// 0 -> "today", 1 -> "1 day ago", 12 -> "12 days ago", null -> "—"
String formatDaysAgo(int? days) {
  if (days == null) return '—';
  if (days <= 0) return 'today';
  if (days == 1) return '1 day ago';
  return '$days days ago';
}

/// 28311552 -> "27.0 MB"; null -> "—"
String formatBytes(int? bytes) {
  if (bytes == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  var value = bytes.toDouble();
  var unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return unit == 0 ? '$bytes B' : '${value.toStringAsFixed(1)} ${units[unit]}';
}

/// 93784 -> "1d 2h 3m", 59 -> "59s"
String formatDuration(int seconds) {
  if (seconds < 60) return '${seconds}s';
  final days = seconds ~/ 86400;
  final hours = (seconds % 86400) ~/ 3600;
  final minutes = (seconds % 3600) ~/ 60;
  final parts = <String>[
    if (days > 0) '${days}d',
    if (days > 0 || hours > 0) '${hours}h',
    '${minutes}m',
  ];
  return parts.join(' ');
}

/// 0.1234 -> "+12.3%", -0.05 -> "-5.0%", null -> "—"
String formatChange(double? change) {
  if (change == null) return '—';
  final percent = (change * 100).toStringAsFixed(1);
  return change > 0 ? '+$percent%' : '$percent%';
}
