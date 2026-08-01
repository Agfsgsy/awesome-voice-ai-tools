import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/core/utils/arabic_text_normalizer.dart';
import 'package:voice_ai_mobile/models/pairing_payload.dart';
import 'package:voice_ai_mobile/models/server_session.dart';
import 'package:voice_ai_mobile/services/api_service.dart';
import 'package:voice_ai_mobile/services/local_document_service.dart';
import 'package:voice_ai_mobile/services/secure_storage_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('يفك رمز اقتران QR الصحيح ويرفض الرمز الناقص', () {
    final payload = PairingPayload.parse(
      'voiceai://pair?server=http%3A%2F%2F192.168.1.5%3A8000&id=1234567890-abcd&code=ABCD-EFGH',
    );
    expect(payload.serverUrl, 'http://192.168.1.5:8000');
    expect(payload.pairingId, '1234567890-abcd');
    expect(payload.code, 'ABCD-EFGH');
    expect(
      () => PairingPayload.parse('voiceai://pair?id=short'),
      throwsA(isA<AppException>()),
    );
  });

  test('يسمح HTTP داخل LAN ويلزم HTTPS خارجيًا', () {
    expect(
      ApiService.normalizeServerUrl('http://192.168.1.8:8000/'),
      'http://192.168.1.8:8000',
    );
    expect(
      ApiService.normalizeServerUrl('https://voice.example.com/api'),
      'https://voice.example.com',
    );
    expect(
      () => ApiService.normalizeServerUrl('http://voice.example.com'),
      throwsA(isA<AppException>()),
    );
  });

  test('يعرض خطأ عربيًا عند انقطاع الشبكة', () {
    final error = DioException(
      requestOptions: RequestOptions(path: '/status'),
      type: DioExceptionType.connectionError,
      error: const SocketException('offline'),
    );
    final result = AppException.fromDio(error);
    expect(result.message, contains('الخادم غير متصل'));
    expect(result.retryable, isTrue);
  });

  test('يحفظ الجلسة والأسرار عبر flutter_secure_storage', () async {
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
    final storage = SecureStorageService();
    final session = ServerSession(
      serverUrl: 'https://voice.example.com',
      deviceId: 'device-1234567890',
      deviceToken: 'device-token-that-is-long-and-private',
      accessToken: 'access-token-private',
      expiresAt: DateTime.utc(2030),
    );
    await storage.saveSession(session);
    await storage.writeSecret('gemini_api_key', 'secret-test-key');
    expect((await storage.readSession())?.deviceId, session.deviceId);
    expect(await storage.readSecret('gemini_api_key'), 'secret-test-key');
    await storage.clearSession();
    expect(await storage.readSession(), isNull);
  });

  test('يستخرج ملف TXT محليًا دون خادم', () async {
    final directory = Directory.systemTemp.createTempSync(
      'voice_ai_document_test',
    );
    addTearDown(() => directory.deleteSync(recursive: true));
    final file = File('${directory.path}/arabic.txt');
    await file.writeAsString('هذا مستند عربي يعمل على الهاتف.');
    final text = await LocalDocumentService().extractText(file.path);
    expect(text, contains('مستند عربي'));
  });

  test('يحوّل الأرقام والتواريخ والعملات إلى قراءة عربية', () {
    const normalizer = ArabicTextNormalizer();
    final result = normalizer.normalize('الموعد 12/08/2026 والمبلغ 125 ر.س');
    expect(result, contains('أغسطس'));
    expect(result, contains('ريالًا سعوديًا'));
    expect(result, isNot(contains('125')));
  });
}
