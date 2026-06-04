import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

/// 词库加载失败提示面板
///
/// 设计原则：
/// - 错误恢复路径清晰（主按钮 + 备选方案）
/// - 视觉层次：图标 → 标题 → 描述 → 行动按钮
/// - 动画时长 150-300ms，ease-out 缓动
/// - 触控目标 ≥44pt，按钮间距 ≥8dp
/// - 保持游戏玻璃态风格一致
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
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
      decoration: BoxDecoration(
        color: AppColors.glassPanelBg,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppColors.dangerNoticeBorder,
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.danger.withOpacity(0.08),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 图标 + 标题行
          _buildHeader(),
          const SizedBox(height: 12),
          // 错误描述
          _buildErrorDescription(),
          const SizedBox(height: 24),
          // 行动按钮
          _buildActionButtons(),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    return const Row(
      children: [
        // 错误图标 - 使用发光效果增加视觉层次
        SizedBox(
          width: 44,
          height: 44,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.dangerNoticeBg,
              borderRadius: BorderRadius.all(Radius.circular(12)),
            ),
            child: Icon(
              Icons.cloud_off_rounded,
              size: 24,
              color: AppColors.danger,
            ),
          ),
        ),
        SizedBox(width: 12),
        // 标题
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                AppStrings.puzzleLoadFailed,
                style: TextStyle(
                  fontFamily: 'NotoSansSC',
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                  letterSpacing: 0.3,
                ),
              ),
              SizedBox(height: 2),
              Text(
                '无法获取游戏词库数据',
                style: TextStyle(
                  fontFamily: 'NotoSansSC',
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildErrorDescription() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.dangerNoticeBg.withOpacity(0.5),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        error,
        style: const TextStyle(
          fontFamily: 'NotoSansSC',
          fontSize: 11,
          fontWeight: FontWeight.w500,
          color: AppColors.dangerText,
          height: 1.4,
        ),
        maxLines: 3,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }

  Widget _buildActionButtons() {
    return Column(
      children: [
        // 主按钮 - 重试（更醒目）
        SizedBox(
          width: double.infinity,
          height: 48, // 触控目标 ≥44pt
          child: ElevatedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh_rounded, size: 20),
            label: const Text(
              '重新加载',
              style: TextStyle(
                fontFamily: 'NotoSansSC',
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primaryTeal,
              foregroundColor: Colors.white,
              elevation: 0,
              shadowColor: AppColors.primaryTealShadow,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        // 备选方案 - 连接服务器（次要按钮）
        SizedBox(
          width: double.infinity,
          height: 44,
          child: OutlinedButton.icon(
            onPressed: onConnectServer,
            icon: const Icon(
              Icons.storage_rounded,
              size: 18,
              color: AppColors.textSecondary,
            ),
            label: const Text(
              AppStrings.connectServerPuzzle,
              style: TextStyle(
                fontFamily: 'NotoSansSC',
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: AppColors.textSecondary,
              ),
            ),
            style: OutlinedButton.styleFrom(
              backgroundColor: AppColors.neutralSurface,
              side: const BorderSide(
                color: AppColors.neutralBorder,
                width: 1,
              ),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          ),
        ),
      ],
    );
  }
}