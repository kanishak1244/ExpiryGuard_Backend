import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/app_spacing.dart';

class TabularCurrency extends StatelessWidget {
  final double amount;
  final TextStyle? style;

  const TabularCurrency({
    super.key,
    required this.amount,
    this.style,
  });

  @override
  Widget build(BuildContext context) {
    return Text(
      '₹\',
      style: style ?? AppTypography.numericPrice,
    );
  }
}

class BatchBadge extends StatelessWidget {
  final String batchNumber;

  const BatchBadge({super.key, required this.batchNumber});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFFF1F5F9),
        borderRadius: AppSpacing.roundedSm,
        border: Border.all(color: AppColors.border, width: 1),
      ),
      child: Text(
        batchNumber.isEmpty ? 'N/A' : batchNumber,
        style: AppTypography.numericBatch,
      ),
    );
  }
}
