import 'package:flutter_test/flutter_test.dart';
import 'package:guess/services/puzzle_repository.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('loads playable puzzles with normalized hint counts', () async {
    const repository = PuzzleRepository();
    final puzzles = await repository.loadPuzzles();

    expect(puzzles, isNotEmpty);
    for (final puzzle in puzzles) {
      expect(puzzle.answer.runes.length, inInclusiveRange(2, 5));
      final prepared = repository.preparePuzzle(puzzle);
      expect(prepared.hints, hasLength(7));
      expect(prepared.hints.toSet(), hasLength(prepared.hints.length));
    }
  });
}
