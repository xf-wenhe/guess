import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

/// 词库加载失败提示条
class PuzzleErrorBanner extends StatelessWidget {
  const PuzzleErrorBanner({
    super.key,
    required this.error,
    required this.onRetry,
    required this.onConnectServer,
  });

  final String error;
  final VoidCallback onRetry;
  final VoidCallback onConnectServer;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.errorBackground,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              const Icon(Icons.warning_amber, color: AppColors.error),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  AppStrings.puzzleLoadFailed,
                  style: AppTextStyles.statusCaption.copyWith(color: AppColors.error),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            error,
            style: AppTextStyles.statusCaption.copyWith(color: AppColors.errorLight),
          ),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              ElevatedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: Text(AppStrings.retry),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.surface,
                  foregroundColor: AppColors.textPrimary,
                ),
              ),
              ElevatedButton.icon(
                onPressed: onConnectServer,
                icon: const Icon(Icons.cloud),
                label: Text(AppStrings.connectServerPuzzle),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primaryTeal,
                  foregroundColor: Colors.white,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}