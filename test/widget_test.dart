// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:guess/app.dart';
import 'package:guess/resources/resources.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('初始界面展示标题、提示和输入框', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const GuessApp(autoStartLocalEmbedding: false));
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 500));
    });
    await tester.pump();

    expect(find.text(AppStrings.homeTitle), findsOneWidget);
    expect(find.text(AppStrings.attemptsLeft), findsOneWidget);
    expect(find.text(AppStrings.hintTitle), findsOneWidget);
    expect(find.byType(EditableText), findsOneWidget);
  });
}
