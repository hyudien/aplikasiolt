import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:olt_control/pages/search_page.dart';

void main() {
  testWidgets('search page prompts for a keyword', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: SearchPage()));

    expect(find.text('Masukkan kata kunci pencarian.'), findsOneWidget);
  });
}
