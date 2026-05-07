// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';
import 'package:guess/app.dart';

void main() {
  testWidgets('初始界面展示标题、提示和输入框', (tester) async {
    await tester.pumpWidget(const GuessApp());

    expect(find.text('词语猜谜'), findsOneWidget);
    expect(find.text('共有 6 次机会'), findsOneWidget);
    expect(find.text('提示逐步揭晓'), findsOneWidget);
    expect(find.text('请输入你的猜测'), findsOneWidget);
  });
}
