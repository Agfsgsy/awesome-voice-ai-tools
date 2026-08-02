import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:voice_ai_mobile/app/app.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('يفتح التطبيق على جهاز Android باتجاه RTL', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: VoiceAiMobileApp()));
    await tester.pumpAndSettle(const Duration(seconds: 3));
    final directionality = tester.widget<Directionality>(find.byType(Directionality).first);
    expect(directionality.textDirection, TextDirection.rtl);
    expect(find.byType(MaterialApp), findsOneWidget);
  });
}
