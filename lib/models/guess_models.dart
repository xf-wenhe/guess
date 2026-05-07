import 'package:guess/resources/resources.dart';

class GuessPuzzle {
  const GuessPuzzle({
    required this.answer,
    required this.hints,
    required this.category,
    this.pos = AppStrings.defaultPos,
  });

  final String answer;
  final List<String> hints; // 按 30% 起，每次递增 10%，共 7 条
  final String category;
  final String pos;
}

class GuessResult {
  GuessResult({required this.word, required this.match});

  final String word;
  final int match;
}
