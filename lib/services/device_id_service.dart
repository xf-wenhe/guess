import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart';

/// 设备唯一 ID 生成服务
class DeviceIdService {
  DeviceIdService._();

  static final DeviceInfoPlugin _deviceInfo = DeviceInfoPlugin();
  static String? _cachedDeviceId;

  /// 获取设备唯一 ID（32字符 hex）
  static Future<String> getDeviceId() async {
    if (_cachedDeviceId != null) {
      return _cachedDeviceId!;
    }

    String deviceIdentifier;
    const appNameSalt = 'guess_game_v1';

    try {
      if (defaultTargetPlatform == TargetPlatform.macOS) {
        final info = await _deviceInfo.macOsInfo;
        deviceIdentifier = info.systemGUID ?? 'macos_${info.model}';
      } else if (defaultTargetPlatform == TargetPlatform.iOS) {
        final info = await _deviceInfo.iosInfo;
        deviceIdentifier = info.identifierForVendor ?? 'ios_${info.model}';
      } else if (defaultTargetPlatform == TargetPlatform.windows) {
        final info = await _deviceInfo.windowsInfo;
        deviceIdentifier = info.deviceId;
      } else if (defaultTargetPlatform == TargetPlatform.linux) {
        final info = await _deviceInfo.linuxInfo;
        deviceIdentifier = info.machineId ?? 'linux_${info.id}';
      } else if (defaultTargetPlatform == TargetPlatform.android) {
        final info = await _deviceInfo.androidInfo;
        deviceIdentifier = info.id;
      } else {
        deviceIdentifier = 'unknown_${DateTime.now().millisecondsSinceEpoch}';
      }
    } catch (e) {
      debugPrint('[DeviceIdService] 获取设备信息失败: $e');
      deviceIdentifier = 'fallback_${DateTime.now().millisecondsSinceEpoch}';
    }

    // SHA256 哈希生成固定长度 ID
    final bytes = utf8.encode('${deviceIdentifier}_$appNameSalt');
    final digest = sha256.convert(bytes);
    _cachedDeviceId = digest.toString().substring(0, 32);

    debugPrint('[DeviceIdService] 设备ID: $_cachedDeviceId');
    return _cachedDeviceId!;
  }

  /// 清除缓存（用于测试）
  static void clearCache() {
    _cachedDeviceId = null;
  }
}
