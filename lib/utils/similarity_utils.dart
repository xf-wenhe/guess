import 'dart:math';

int calculateSimilarity(String guess, String target) {
  final guessChars = guess.runes.toList();
  final targetChars = target.runes.toList();
  final Map<int, int> freqGuess = {};
  final Map<int, int> freqTarget = {};

  for (final c in guessChars) {
    freqGuess[c] = (freqGuess[c] ?? 0) + 1;
  }
  for (final c in targetChars) {
    freqTarget[c] = (freqTarget[c] ?? 0) + 1;
  }

  int common = 0;
  for (final entry in freqGuess.entries) {
    final other = freqTarget[entry.key];
    if (other != null) {
      common += min(entry.value, other);
    }
  }

  int positionMatch = 0;
  final minLen = min(guessChars.length, targetChars.length);
  for (var i = 0; i < minLen; i++) {
    if (guessChars[i] == targetChars[i]) {
      positionMatch++;
    }
  }

  final score = (common * 0.6 + positionMatch * 0.4) /
      max(targetChars.length, guessChars.length);
  return (score * 100).clamp(0, 100).round();
}

double cosineSimilarity(List<double> a, List<double> b) {
  final length = min(a.length, b.length);
  double dot = 0;
  double normA = 0;
  double normB = 0;
  for (var i = 0; i < length; i++) {
    final av = a[i];
    final bv = b[i];
    dot += av * bv;
    normA += av * av;
    normB += bv * bv;
  }
  if (normA == 0 || normB == 0) {
    return 0;
  }
  return (dot / (sqrt(normA) * sqrt(normB))).clamp(0, 1);
}

int normalizeSimilarity(int similarity) {
  // 限制逻辑：
  // 1. 相似度在 20-40% 之间时，显示为 10-20%
  // 2. 相似度 >= 95% 时限制为 95%（答案不同时不显示完全匹配）
  int normalized = max(10, min(100, similarity));
  
  if (normalized >= 95) {
    return 95;
  }
  if (normalized >= 20 && normalized <= 40) {
    // 线性映射 [20, 40] -> [10, 20]
    return 10 + ((normalized - 20) * 10 ~/ 20);
  }
  
  return normalized;
}

int semanticPercent(double cosine) {
  final clamped = cosine.clamp(0.0, 1.0);
  return (clamped * 100).round();
}
