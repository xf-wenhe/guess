import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// 连接状态
enum ConnectionStatus {
  connected,
  disconnected,
}

/// 连接探测结果
class ConnectionProbeResult {
  const ConnectionProbeResult({
    required this.status,
    this.endpoint,
    this.latencyMs,
    this.errorMessage,
  });

  final ConnectionStatus status;
  final String? endpoint;
  final int? latencyMs;
  final String? errorMessage;
}

/// 连接日志工具
class ConnectionLog {
  ConnectionLog._();

  static void info(String tag, String message, [Map<String, dynamic>? data]) {
    final timestamp = DateTime.now().toIso8601String();
    final dataStr = data != null ? ' | ${_formatData(data)}' : '';
    final logMessage = '[$timestamp] [$tag] $message$dataStr';
    debugPrint('[Guess] $logMessage');
  }

  static void error(String tag, String message, [Object? error]) {
    final timestamp = DateTime.now().toIso8601String();
    final errorStr = error != null ? ' | Error: $error' : '';
    final logMessage = '[$timestamp] [$tag] ERROR: $message$errorStr';
    debugPrint('[Guess] $logMessage');
  }

  static String _formatData(Map<String, dynamic> data) {
    return data.entries.map((e) => '${e.key}=${e.value}').join(', ');
  }
}

/// 连接服务（统一管理模型和词库连接）
class ConnectionService {
  ConnectionService({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  String? _connectedEmbedEndpoint;
  String? _connectedPuzzleEndpoint;

  String? get connectedEmbedEndpoint => _connectedEmbedEndpoint;
  String? get connectedPuzzleEndpoint => _connectedPuzzleEndpoint;

  /// 按优先级探测模型端点：局域网 → 公网
  Future<ConnectionProbeResult> probeEmbedEndpoints({
    required List<String> lanEndpoints,
    required String publicEndpoint,
  }) async {
    ConnectionLog.info('Embed', '开始探测模型端点', {
      'lanCount': lanEndpoints.length,
    });

    // 1. 尝试局域网端点
    for (final endpoint in lanEndpoints) {
      final result = await _probeEndpoint(endpoint, 'Embed');
      if (result.status == ConnectionStatus.connected) {
        _connectedEmbedEndpoint = endpoint;
        ConnectionLog.info('Embed', '局域网连接成功', {
          'endpoint': endpoint,
          'latencyMs': result.latencyMs,
        });
        return result;
      }
    }

    // 2. 尝试公网端点
    final publicResult = await _probeEndpoint(publicEndpoint, 'Embed');
    if (publicResult.status == ConnectionStatus.connected) {
      _connectedEmbedEndpoint = publicEndpoint;
      ConnectionLog.info('Embed', '公网连接成功', {
        'endpoint': publicEndpoint,
        'latencyMs': publicResult.latencyMs,
      });
      return publicResult;
    }

    // 3. 所有端点均失败
    ConnectionLog.error('Embed', '所有模型端点连接失败');
    _connectedEmbedEndpoint = null;
    return const ConnectionProbeResult(
      status: ConnectionStatus.disconnected,
      errorMessage: '无法连接到模型服务',
    );
  }

  /// 按优先级探测词库端点：局域网 → 公网
  Future<ConnectionProbeResult> probePuzzleEndpoints({
    required List<String> lanEndpoints,
    required String publicEndpoint,
  }) async {
    ConnectionLog.info('Puzzle', '开始探测词库端点', {
      'lanCount': lanEndpoints.length,
    });

    // 1. 尝试局域网端点
    for (final endpoint in lanEndpoints) {
      final result = await _probeEndpoint(endpoint, 'Puzzle');
      if (result.status == ConnectionStatus.connected) {
        _connectedPuzzleEndpoint = endpoint;
        ConnectionLog.info('Puzzle', '局域网连接成功', {
          'endpoint': endpoint,
          'latencyMs': result.latencyMs,
        });
        return result;
      }
    }

    // 2. 尝试公网端点
    final publicResult = await _probeEndpoint(publicEndpoint, 'Puzzle');
    if (publicResult.status == ConnectionStatus.connected) {
      _connectedPuzzleEndpoint = publicEndpoint;
      ConnectionLog.info('Puzzle', '公网连接成功', {
        'endpoint': publicEndpoint,
        'latencyMs': publicResult.latencyMs,
      });
      return publicResult;
    }

    ConnectionLog.error('Puzzle', '所有词库端点连接失败');
    _connectedPuzzleEndpoint = null;
    return const ConnectionProbeResult(
      status: ConnectionStatus.disconnected,
      errorMessage: '无法连接到词库服务',
    );
  }

  /// 探测单个端点
  Future<ConnectionProbeResult> _probeEndpoint(String endpoint, String tag) async {
    final stopwatch = Stopwatch()..start();
    try {
      final uri = Uri.parse(endpoint);
      // 将 /embed 或 /puzzles 替换为 /health
      final healthPath = uri.path.replaceAll(RegExp(r'/(embed|puzzles)$'), '/health');
      final healthUri = uri.replace(path: healthPath);

      final response = await _client
          .get(healthUri)
          .timeout(const Duration(seconds: 3));

      stopwatch.stop();

      if (response.statusCode == 200) {
        return ConnectionProbeResult(
          status: ConnectionStatus.connected,
          endpoint: endpoint,
          latencyMs: stopwatch.elapsedMilliseconds,
        );
      } else {
        ConnectionLog.info(tag, '端点返回非200状态', {
          'endpoint': endpoint,
          'statusCode': response.statusCode,
        });
        return ConnectionProbeResult(
          status: ConnectionStatus.disconnected,
          errorMessage: 'HTTP ${response.statusCode}',
        );
      }
    } catch (e) {
      stopwatch.stop();
      ConnectionLog.info(tag, '端点连接失败', {
        'endpoint': endpoint,
        'error': e.toString(),
        'latencyMs': stopwatch.elapsedMilliseconds,
      });
      return ConnectionProbeResult(
        status: ConnectionStatus.disconnected,
        errorMessage: e.toString(),
      );
    }
  }

  /// 清除连接状态
  void clearConnection() {
    _connectedEmbedEndpoint = null;
    _connectedPuzzleEndpoint = null;
  }

  void dispose() {
    _client.close();
  }
}