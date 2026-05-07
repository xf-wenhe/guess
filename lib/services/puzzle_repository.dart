import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:guess/resources/resources.dart';

import '../models/guess_models.dart';

class PuzzleRepository {
  const PuzzleRepository();

  static final RegExp _containsCjk = RegExp(r'[\u4e00-\u9fff]');
  static const Map<String, String> _naturalHintRewrites = {};

  static const List<String> _genericHints = AppStrings.genericHints;

  Future<List<GuessPuzzle>> loadPuzzles() async {
    final raw = await rootBundle.loadString(AppAssets.puzzles);
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
