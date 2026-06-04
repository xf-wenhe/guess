import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// 统计汇总
class StatisticsSummary {
  const StatisticsSummary({
    required this.correctCount,
    required this.wrongCount,
    required this.totalCount,
    required this.accuracy,
  });

  final int correctCount;
  final int wrongCount;
  final int totalCount;
  final double accuracy;

  factory StatisticsSummary.fromJson(Map<String, dynamic> json) {
    return StatisticsSummary(
      correctCount: json['correct_count'] as int,
      wrongCount: json['wrong_count'] as int,
      totalCount: json['total_count'] as int,
      accuracy: (json['accuracy'] as num).toDouble(),
    );
  }
}

/// 今日统计
class TodayStatistics {
  const TodayStatistics({
    required this.correctCount,
    required this.wrongCount,
    required this.totalCount,
  });

  final int correctCount;
  final int wrongCount;
  final int totalCount;

  factory TodayStatistics.fromJson(Map<String, dynamic> json) {
    return TodayStatistics(
      correctCount: json['correct_count'] as int,
      wrongCount: json['wrong_count'] as int,
      totalCount: json['total_count'] as int,
    );
  }
}

/// 统计服务 HTTP 客户端
class StatisticsService {
  StatisticsService({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  String? _baseUrl;

  void setBaseUrl(String baseUrl) {
    _baseUrl = baseUrl;
  }

  /// 获取统计汇总
  Future<StatisticsSummary?> getSummary(int userId) async {
    if (_baseUrl == null) return null;

    try {
      final response = await _client
          .get(Uri.parse('$_baseUrl/api/stats/summary/$userId'))
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        if (json['success'] == true) {
          return StatisticsSummary.fromJson(
            json['summary'] as Map<String, dynamic>,
          );
        }
      }
      return null;
    } catch (e) {
      debugPrint('[StatisticsService] 获取统计汇总失败: $e');
      return null;
    }
  }

  /// 获取今日统计
  Future<TodayStatistics?> getToday(int userId) async {
    if (_baseUrl == null) return null;

    try {
      final response = await _client
          .get(Uri.parse('$_baseUrl/api/stats/today/$userId'))
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        if (json['success'] == true) {
          return TodayStatistics.fromJson(
            json['today'] as Map<String, dynamic>,
          );
        }
      }
      return null;
    } catch (e) {
      debugPrint('[StatisticsService] 获取今日统计失败: $e');
      return null;
    }
  }

  /// 记录答题结果
  Future<bool> recordGame({
    required int userId,
    required bool correct,
    required int hintIndex,
  }) async {
    if (_baseUrl == null) return false;

    final today = DateTime.now().toIso8601String().split('T')[0];

    try {
      final response = await _client
          .post(
            Uri.parse('$_baseUrl/api/stats/record'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'user_id': userId,
              'correct': correct,
              'date': today,
              'hint_index': hintIndex,
            }),
          )
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        return json['success'] == true;
      }
      return false;
    } catch (e) {
      debugPrint('[StatisticsService] 记录答题失败: $e');
      return false;
    }
  }

  void dispose() {
    _client.close();
  }
}