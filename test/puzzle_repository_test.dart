import 'package:flutter_test/flutter_test.dart';
import 'package:guess/models/guess_models.dart';
import 'package:guess/services/puzzle_repository.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('PuzzleRepository throws when no source configured', () async {
    final repository = PuzzleRepository();
    // 没有配置本地路径或网络端点，应该抛出异常
    expect(
      () => repository.loadPuzzles(),
      throwsA(isA<PuzzleLoadException>()),
    );
  });

  test('preparePuzzle pads hints to 7', () async {
    final repository = PuzzleRepository();
    final puzzle = GuessPuzzle(
      answer: '测试',
      hints: ['提示一', '提示二'],
      category: '测试分类',
      pos: '名词',
    );
    final prepared = repository.preparePuzzle(puzzle);
    expect(prepared.hints, hasLength(7));
    expect(prepared.hints.toSet(), hasLength(prepared.hints.length));
  });
}