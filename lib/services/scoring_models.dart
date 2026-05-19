class ScoreTraceEvent {
  const ScoreTraceEvent({
    required this.event,
    required this.guess,
    required this.answer,
    required this.finalScore,
    this.semanticRaw,
    this.semanticPercentRaw,
    this.semanticPercentCalibrated,
    this.lexical,
    this.combined,
    this.notes = const [],
  });

  final String event;
  final String guess;
  final String answer;
  final int finalScore;
  final double? semanticRaw;
  final double? semanticPercentRaw;
  final double? semanticPercentCalibrated;
  final int? lexical;
  final int? combined;
  final List<String> notes;
}

class ScoreResult {
  const ScoreResult({required this.score, required this.source});

  final int score;
  final String? source;
}

class CalibrationCurve {
  const CalibrationCurve({required this.x, required this.y});

  final List<double> x;
  final List<double> y;

  factory CalibrationCurve.fromJson(Map<String, dynamic> decoded) {
    final x = (decoded['x_pred'] as List<dynamic>?)
        ?.map((e) => (e as num).toDouble())
        .toList();
    final y = (decoded['y_calibrated'] as List<dynamic>?)
        ?.map((e) => (e as num).toDouble())
        .toList();
    if (x == null || y == null || x.length != y.length || x.length < 2) {
      throw const FormatException('invalid calibration curve');
    }

    final pairs = <MapEntry<double, double>>[];
    for (var i = 0; i < x.length; i += 1) {
      pairs.add(MapEntry(x[i], y[i]));
    }
    pairs.sort((a, b) => a.key.compareTo(b.key));
    return CalibrationCurve(
      x: pairs.map((e) => e.key).toList(growable: false),
      y: pairs.map((e) => e.value).toList(growable: false),
    );
  }

  double apply(double percent) {
    if (x.length != y.length || x.length < 2) {
      return percent;
    }

    if (percent <= x.first) return y.first;
    if (percent >= x.last) return y.last;

    for (var i = 0; i < x.length - 1; i += 1) {
      final left = x[i];
      final right = x[i + 1];
      if (percent < left || percent > right) {
        continue;
      }
      final span = right - left;
      if (span == 0) {
        return y[i];
      }
      final t = (percent - left) / span;
      return y[i] + (y[i + 1] - y[i]) * t;
    }
    return percent;
  }
}

class ManualSimilarityOverrides {
  ManualSimilarityOverrides([Map<String, int>? values])
      : _values = Map<String, int>.from(values ?? const {});

  final Map<String, int> _values;

  factory ManualSimilarityOverrides.fromJson(Object? decoded) {
    if (decoded is! List) {
      return ManualSimilarityOverrides();
    }
    final values = <String, int>{};
    for (final item in decoded) {
      if (item is! Map<String, dynamic>) {
        continue;
      }
      final answer = (item['answer'] as String? ?? '').trim();
      final userInput = (item['user_input'] as String? ?? '').trim();
      final scoreRaw = item['score'];
      if (answer.isEmpty || userInput.isEmpty || scoreRaw is! num) {
        continue;
      }
      values[_pairKey(answer, userInput)] = scoreRaw.round().clamp(0, 95);
    }
    return ManualSimilarityOverrides(values);
  }

  int? score({required String guess, required String answer}) {
    return _values[_pairKey(answer, guess)] ?? _values[_pairKey(guess, answer)];
  }

  static String _pairKey(String a, String b) => '$a\t$b';
}
