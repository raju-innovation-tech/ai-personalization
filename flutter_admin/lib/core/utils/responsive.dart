import 'package:flutter/material.dart';

import '../constants/app_constants.dart';

enum ScreenSize { mobile, tablet, desktop }

class Responsive {
  Responsive._();

  static ScreenSize of(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    if (width < AppConstants.mobileBreakpoint) return ScreenSize.mobile;
    if (width < AppConstants.tabletBreakpoint) return ScreenSize.tablet;
    return ScreenSize.desktop;
  }

  static bool isMobile(BuildContext context) => of(context) == ScreenSize.mobile;
  static bool isTablet(BuildContext context) => of(context) == ScreenSize.tablet;
  static bool isDesktop(BuildContext context) => of(context) == ScreenSize.desktop;
  static bool isWide(BuildContext context) => MediaQuery.sizeOf(context).width >= AppConstants.desktopBreakpoint;

  /// Adaptive padding based on screen width
  static EdgeInsets contentPadding(BuildContext context) {
    if (isMobile(context)) return const EdgeInsets.symmetric(horizontal: 14, vertical: 12);
    if (isTablet(context)) return const EdgeInsets.all(18);
    return const EdgeInsets.all(24);
  }

  /// Adaptive grid column count for cards
  static int gridColumns(BuildContext context, {int mobile = 1, int tablet = 2, int desktop = 4}) {
    if (isMobile(context)) return mobile;
    if (isTablet(context)) return tablet;
    return desktop;
  }
}

/// Builds a different widget per breakpoint. Any omitted breakpoint
/// falls back to the next-smaller one that was provided.
class ResponsiveBuilder extends StatelessWidget {
  const ResponsiveBuilder({super.key, required this.mobile, this.tablet, this.desktop});

  final WidgetBuilder mobile;
  final WidgetBuilder? tablet;
  final WidgetBuilder? desktop;

  @override
  Widget build(BuildContext context) {
    final size = Responsive.of(context);
    switch (size) {
      case ScreenSize.desktop:
        return (desktop ?? tablet ?? mobile)(context);
      case ScreenSize.tablet:
        return (tablet ?? mobile)(context);
      case ScreenSize.mobile:
        return mobile(context);
    }
  }
}
