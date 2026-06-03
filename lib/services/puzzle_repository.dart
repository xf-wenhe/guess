import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models/guess_models.dart';
import '../resources/resources.dart';
import 'connection_service.dart' show ConnectionLog;

/// 词库加载异常
class PuzzleLoadException implements Exception {
  final String message;
  PuzzleLoadException(this.message);

  @override
  String toString() => 'PuzzleLoadException: $message';
}

class PuzzleRepository {
  PuzzleRepository();

  static final RegExp _containsCjk = RegExp(r'[一-鿿]');
  static const Map<String, String> _naturalHintRewrites = {};

  static const List<String> _genericHints = AppStrings.genericHints;

  String? _activeEndpoint;
  String? _localPuzzlePath;

  /// 设置网络词库端点（由 ConnectionService 探测后设置）
  void setActiveEndpoint(String endpoint) {
    _activeEndpoint = endpoint;
  }

  /// 设置本地词库路径（由用户设置）
  void setLocalPuzzlePath(String path) {
    _localPuzzlePath = path.trim().isEmpty ? null : path.trim();
  }

  /// 加载词库，优先级：本地路径 > 网络端点 > 抛出异常
  Future<List<GuessPuzzle>> loadPuzzles() async {
    String? raw;
    String? errorSource;

    // 1. 优先使用用户设置的本地词库路径
    if (_localPuzzlePath != null && _localPuzzlePath!.isNotEmpty) {
      try {
        final file = File(_localPuzzlePath!);
        if (await file.exists()) {
          raw = await file.readAsString();
          ConnectionLog.info('Puzzle', '本地词库加载成功', {
            'path': _localPuzzlePath!,
          });
        } else {
          errorSource = '本地词库文件不存在: $_localPuzzlePath';
        }
      } catch (e) {
        errorSource = '本地词库读取失败: $e';
        ConnectionLog.error('Puzzle', '本地词库读取失败', e);
      }
    }

    // 2. 尝试网络端点（由 ConnectionService 探测后的可用端点）
    if (raw == null && _activeEndpoint != null) {
      try {
        final response = await http
            .get(Uri.parse(_activeEndpoint!))
            .timeout(const Duration(seconds: 10));
        if (response.statusCode == 200) {
          raw = response.body;
          ConnectionLog.info('Puzzle', '网络词库加载成功', {
            'endpoint': _activeEndpoint!,
            'size': response.body.length,
          });
        } else {
          errorSource = '网络词库返回 HTTP ${response.statusCode}';
          ConnectionLog.error('Puzzle', '网络词库返回非200状态', null);
        }
      } catch (e) {
        errorSource = '网络词库连接失败: $e';
        ConnectionLog.error('Puzzle', '网络词库连接失败', e);
      }
    }

    // 3. 无 fallback，全部失败时抛出异常
    if (raw == null) {
      throw PuzzleLoadException(errorSource ?? '未配置词库源，请在设置中配置本地词库路径');
    }

    final List<dynamic> data = jsonDecode(raw) as List<dynamic>;
    final puzzles = <GuessPuzzle>[];
    for (final e in data) {
      final answer = (e['answer'] as String?)?.trim();
      if (answer == null || answer.isEmpty) continue;
      final rawHints = e['hints'] as List<dynamic>?;
      if (rawHints == null || rawHints.isEmpty) continue;
      final pos = (e['pos'] as String? ?? AppStrings.defaultPos).trim();
      final category =
          (e['category'] as String? ?? AppStrings.defaultCategory).trim();
      final hints = <String>[];
      final seen = <String>{};
      for (final rawHint in rawHints.whereType<String>()) {
        if (hints.length >= 7) {
          break;
        }
        final normalized = _normalizeHint(
          rawHint,
          answer: answer,
          category: category,
        );
        if (normalized.isEmpty || !_isHintUsable(normalized)) {
          continue;
        }
        if (seen.add(normalized)) {
          hints.add(normalized);
        }
      }
      if (hints.isEmpty) continue;
      if (answer.length < 2 || answer.length > 5) continue;
      puzzles.add(
        GuessPuzzle(
          answer: answer,
          hints: hints,
          category: category.isEmpty ? AppStrings.defaultCategory : category,
          pos: pos,
        ),
      );
    }
    return puzzles;
  }

  static String _normalizeHint(
    String hint, {
    required String answer,
    required String category,
  }) {
    var normalized = hint.trim().replaceAll(RegExp(r'\s+'), '');
    if (normalized.isEmpty) {
      return '';
    }

    final mapped = _naturalHintRewrites[normalized];
    if (mapped != null) {
      normalized = mapped;
    }

    if (normalized == answer) {
      return '';
    }

    if (normalized.length < 2 &&
        (category == '成语' || category == '典故' || category == '歇后语')) {
      return '';
    }

    return normalized;
  }

  GuessPuzzle preparePuzzle(GuessPuzzle base) {
    const targetCount = 7;
    final result = <String>[];

    bool push(String h) {
      if (!result.contains(h)) {
        result.add(h);
        return true;
      }
      return false;
    }

    for (final h in base.hints) {
      if (result.length >= targetCount) break;
      push(h);
    }

    if (result.length < targetCount) {
      for (final h in _genericHints) {
        if (result.length >= targetCount) break;
        push(h);
      }
    }

    while (result.length < targetCount) {
      push('再换个思路 ${result.length + 1}');
    }

    return GuessPuzzle(
      answer: base.answer,
      hints: result,
      category: base.category,
      pos: base.pos,
    );
  }

  static bool _isHintUsable(String hint) {
    final len = hint.runes.length;
    if (len < 2 || len > 8) {
      return false;
    }
    return _containsCjk.hasMatch(hint);
  }
}