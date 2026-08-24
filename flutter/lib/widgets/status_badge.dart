import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/app_spacing.dart';

enum BadgeStatus { safe, warning, danger, info }

class StatusBadge extends StatelessWidget {
  final String label;
  final BadgeStatus status;
  final IconData? icon;

  const StatusBadge({
    super.key,
    required this.label,
    this.status = BadgeStatus.safe,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    Color bg;
    Color textColor;
    Color border;

    switch (status) {
      case BadgeStatus.safe:
        bg = AppColors.statusSafeBg;
        textColor = AppColors.statusSafeText;
        border = const Color(0xFFA7F3D0);
        break;
      case BadgeStatus.warning:
        bg = AppColors.statusWarningBg;
        textColor = AppColors.statusWarningText;
        border = const Color(0xFFFDE68A);
        break;
      case BadgeStatus.danger:
        bg = AppColors.statusDangerBg;
        textColor = AppColors.statusDangerText;
        border = const Color(0xFFFECACA);
        break;
      case BadgeStatus.info:
        bg = AppColors.statusInfoBg;
        textColor = AppColors.statusInfoText;
        border = const Color(0xFFBAE6FD);
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: AppSpacing.roundedSm,
        border: Border.all(color: border, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 12, color: textColor),
            const SizedBox(width: 4),
          ],
          Text(
            label,
            style: AppTypography.badge.copyWith(color: textColor),
          ),
        ],
      ),
    );
  }
}
