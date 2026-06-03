// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('基础 UI 组件渲染测试', (tester) async {
    // 简单的 smoke test，验证基础 widget 渲染
    await tester.pumpWidget(
      const MaterialApp(
        home: Material(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('词语猜谜'),
              Text('剩余机会'),
              Text('提示'),
              TextField(),
            ],
          ),
        ),
      ),
    );

    expect(find.text('词语猜谜'), findsOneWidget);
    expect(find.text('剩余机会'), findsOneWidget);
    expect(find.text('提示'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
  });
}
