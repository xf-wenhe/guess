import 'package:flutter/material.dart';
import 'package:guess/controllers/account_controller.dart';
import 'package:guess/resources/resources.dart';
import 'package:guess/services/statistics_service.dart';

/// 用户下拉菜单
class UserProfileMenu extends StatelessWidget {
  const UserProfileMenu({super.key, required this.controller});

  final AccountController controller;

  @override
  Widget build(BuildContext context) {
    final user = controller.user;
    final stats = controller.statistics;
    final today = controller.todayStatistics;

    return PopupMenuButton<void>(
      position: PopupMenuPosition.under,
      offset: const Offset(0, 8),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      itemBuilder: (context) => [
        PopupMenuItem<void>(
          enabled: false,
          child: _buildUserHeader(user?.nickname ?? AppStrings.unknownUser),
        ),
        const PopupMenuDivider(),
        PopupMenuItem<void>(
          enabled: false,
          child: _buildStatsSection(stats, today),
        ),
      ],
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircleAvatar(
              radius: 14,
              backgroundColor: AppColors.primaryTeal,
              child: Text(
                (user?.nickname ?? '?').substring(0, 1),
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              user?.nickname ?? AppStrings.connectServer,
              style: AppTextStyles.statusCaption,
            ),
            const Icon(Icons.arrow_drop_down, size: 20),
          ],
        ),
      ),
    );
  }

  Widget _buildUserHeader(String nickname) {
    return Row(
      children: [
        CircleAvatar(
          radius: 20,
          backgroundColor: AppColors.primaryTeal,
          child: Text(
            nickname.substring(0, 1),
            style: const TextStyle(color: Colors.white, fontSize: 20),
          ),
        ),
        const SizedBox(width: 12),
        Text(nickname, style: AppTextStyles.panelTitle),
      ],
    );
  }

  Widget _buildStatsSection(StatisticsSummary? stats, TodayStatistics? today) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildStatRow(AppStrings.correctCount, stats?.correctCount ?? 0),
        _buildStatRow(AppStrings.wrongCount, stats?.wrongCount ?? 0),
        _buildStatRow(AppStrings.totalCount, stats?.totalCount ?? 0),
        _buildStatRow(
          AppStrings.accuracy,
          '${stats?.accuracy.toStringAsFixed(1) ?? '0.0'}%',
        ),
        const Divider(),
        _buildStatRow(
          AppStrings.todayStats,
          '${today?.correctCount ?? 0}/${today?.totalCount ?? 0}',
        ),
      ],
    );
  }

  Widget _buildStatRow(String label, dynamic value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: AppTextStyles.statusCaption),
          Text('$value', style: AppTextStyles.statusUnit),
        ],
      ),
    );
  }
}