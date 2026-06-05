import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// 用户模型
class User {
  const User({required this.id, required this.nickname});

  final int id;
  final String nickname;

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] as int,
      nickname: json['nickname'] as String,
    );
  }
}

/// 账号响应
class AccountResponse {
  const AccountResponse({required this.success, this.user, this.error});

  final bool success;
  final User? user;
  final String? error;

  factory AccountResponse.fromJson(Map<String, dynamic> json) {
    return AccountResponse(
      success: json['success'] as bool,
      user: json['user'] != null
          ? User.fromJson(json['user'] as Map<String, dynamic>)
          : null,
      error: json['error'] as String?,
    );
  }
}

/// 账号服务 HTTP 客户端
class AccountService {
  AccountService({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  String? _activeEndpoint;

  String? get activeEndpoint => _activeEndpoint;

  /// 设置活动端点
  void setActiveEndpoint(String endpoint) {
    _activeEndpoint = endpoint.replaceFirst('/api', '');
  }

  /// 探测账号服务可用性
  Future<bool> probe(String baseUrl) async {
    try {
      final response = await _client
          .get(Uri.parse('$baseUrl/health'))
          .timeout(const Duration(seconds: 3));
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('[AccountService] 探测失败: $e');
      return false;
    }
  }

  /// 创建账号
  Future<AccountResponse> createAccount({
    required String deviceId,
    required String nickname,
  }) async {
    if (_activeEndpoint == null) {
      return const AccountResponse(success: false, error: 'no_endpoint');
    }

    try {
      final response = await _client
          .post(
            Uri.parse('$baseUrl/api/account/create'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'device_id': deviceId,
              'nickname': nickname,
            }),
          )
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        // 使用 utf8 解码确保中文字符正确处理
        final body = utf8.decode(response.bodyBytes);
        return AccountResponse.fromJson(
          jsonDecode(body) as Map<String, dynamic>,
        );
      }
      return const AccountResponse(success: false, error: 'http_error');
    } catch (e) {
      debugPrint('[AccountService] 创建账号失败: $e');
      return AccountResponse(success: false, error: e.toString());
    }
  }

  /// 根据设备ID查询账号
  Future<AccountResponse> getAccountByDevice(String deviceId) async {
    if (_activeEndpoint == null) {
      return const AccountResponse(success: false, error: 'no_endpoint');
    }

    try {
      final response = await _client
          .get(Uri.parse('$baseUrl/api/account/by_device/$deviceId'))
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        // 使用 utf8 解码确保中文字符正确处理
        final body = utf8.decode(response.bodyBytes);
        return AccountResponse.fromJson(
          jsonDecode(body) as Map<String, dynamic>,
        );
      }
      return const AccountResponse(success: false, error: 'http_error');
    } catch (e) {
      debugPrint('[AccountService] 查询账号失败: $e');
      return AccountResponse(success: false, error: e.toString());
    }
  }

  /// 更新昵称
  Future<AccountResponse> updateNickname({
    required String deviceId,
    required String nickname,
  }) async {
    if (_activeEndpoint == null) {
      return const AccountResponse(success: false, error: 'no_endpoint');
    }

    try {
      final response = await _client
          .put(
            Uri.parse('$baseUrl/api/account/nickname'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'device_id': deviceId,
              'nickname': nickname,
            }),
          )
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final body = utf8.decode(response.bodyBytes);
        return AccountResponse.fromJson(
          jsonDecode(body) as Map<String, dynamic>,
        );
      }
      return const AccountResponse(success: false, error: 'http_error');
    } catch (e) {
      debugPrint('[AccountService] 更新昵称失败: $e');
      return AccountResponse(success: false, error: e.toString());
    }
  }

  String get baseUrl => _activeEndpoint ?? '';

  void dispose() {
    _client.close();
  }
}