import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/services/api_service.dart';

class _MobileApiFixture {
  _MobileApiFixture._(this.server) {
    serving = _serve();
  }

  final HttpServer server;
  final List<int> audioBytes = utf8.encode('RIFF-mobile-audio-result');
  late final Future<void> serving;
  bool rangeRequestSeen = false;
  int authenticatedRequests = 0;

  String get url => 'http://${server.address.address}:${server.port}';

  static Future<_MobileApiFixture> start() async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    return _MobileApiFixture._(server);
  }

  Future<void> _serve() async {
    await for (final request in server) {
      await _handle(request);
    }
  }

  Future<void> _handle(HttpRequest request) async {
    final path = request.uri.path;
    final body = await utf8.decoder.bind(request).join();
    if (request.headers.value(HttpHeaders.authorizationHeader) == 'Bearer access-token') {
      authenticatedRequests++;
    }
    if (path == '/api/mobile/pair') {
      if (body.contains('expired-session')) {
        await _json(request.response, HttpStatus.badRequest, <String, String>{'detail': 'انتهت صلاحية جلسة الاقتران.'});
      } else {
        await _json(
          request.response,
          HttpStatus.ok,
          <String, String>{'device_id': 'device-1234567890', 'device_token': 'device-token-secure', 'server_url': url},
        );
      }
      return;
    }
    if (path == '/api/mobile/auth') {
      await _json(
        request.response,
        HttpStatus.ok,
        <String, String>{
          'access_token': 'access-token',
          'expires_at': DateTime.now().toUtc().add(const Duration(hours: 1)).toIso8601String(),
        },
      );
      return;
    }
    if (path == '/api/mobile/status') {
      await _json(request.response, HttpStatus.ok, <String, Object>{'status': 'online', 'pairing': true});
      return;
    }
    if (path == '/api/mobile/jobs/job-1' && request.method == 'GET') {
      await _json(request.response, HttpStatus.ok, _job('completed', 100, false));
      return;
    }
    if (path == '/api/mobile/jobs/job-1/cancel') {
      await _json(request.response, HttpStatus.ok, _job('cancelled', 55, false));
      return;
    }
    if (path == '/api/mobile/files/file-1/share') {
      await _json(request.response, HttpStatus.ok, <String, String>{'share_url': '$url/shared/audio'});
      return;
    }
    if (path == '/api/mobile/files/file-1') {
      final range = request.headers.value(HttpHeaders.rangeHeader);
      final start = range == null ? 0 : int.parse(RegExp(r'bytes=(\d+)-').firstMatch(range)!.group(1)!);
      rangeRequestSeen = start > 0;
      final remaining = audioBytes.sublist(start);
      request.response
        ..statusCode = start > 0 ? HttpStatus.partialContent : HttpStatus.ok
        ..contentLength = remaining.length;
      if (start > 0) {
        request.response.headers.set(HttpHeaders.contentRangeHeader, 'bytes $start-${audioBytes.length - 1}/${audioBytes.length}');
      }
      request.response.add(remaining);
      await request.response.close();
      return;
    }
    await _json(request.response, HttpStatus.notFound, <String, String>{'detail': 'غير موجود'});
  }

  Map<String, Object> _job(String status, int progress, bool canCancel) => <String, Object>{
        'job_id': 'job-1',
        'kind': 'voice_synthesis',
        'status': status,
        'progress': progress,
        'message': status == 'cancelled' ? 'المهمة أُلغيت' : 'اكتملت المهمة',
        'can_cancel': canCancel,
        'result': <String, Object>{'file_id': 'file-1'},
      };

  Future<void> _json(HttpResponse response, int status, Object value) async {
    final data = utf8.encode(jsonEncode(value));
    response
      ..statusCode = status
      ..headers.contentType = ContentType.json
      ..contentLength = data.length
      ..add(data);
    await response.close();
  }

  Future<void> close() async {
    await server.close(force: true);
    await serving;
  }
}

void main() {
  test('يقترن ويسجل الدخول ويتصل بخادم FastAPI', () async {
    final fixture = await _MobileApiFixture.start();
    addTearDown(fixture.close);
    final api = ApiService();
    final session = await api.pair(
      serverUrl: fixture.url,
      pairingId: 'valid-session',
      pairingCode: 'ABCD-EFGH',
      deviceName: 'هاتف الاختبار',
    );
    expect(session.deviceId, 'device-1234567890');
    expect((await api.status())['status'], 'online');
    expect(fixture.authenticatedRequests, greaterThanOrEqualTo(1));
  });

  test('يعرض رسالة عربية عند انتهاء جلسة الاقتران', () async {
    final fixture = await _MobileApiFixture.start();
    addTearDown(fixture.close);
    final api = ApiService();
    await expectLater(
      api.pair(
        serverUrl: fixture.url,
        pairingId: 'expired-session',
        pairingCode: 'ABCD-EFGH',
        deviceName: 'هاتف الاختبار',
      ),
      throwsA(isA<AppException>().having((error) => error.message, 'message', contains('انتهت صلاحية'))),
    );
  });

  test('يستأنف تنزيل ملف صوتي جزئي ويشاركه', () async {
    final fixture = await _MobileApiFixture.start();
    addTearDown(fixture.close);
    final directory = await Directory.systemTemp.createTemp('voice_ai_download_test');
    addTearDown(() => directory.delete(recursive: true));
    final destination = '${directory.path}/result.wav';
    await File('$destination.part').writeAsBytes(fixture.audioBytes.take(5).toList());
    final api = ApiService()..configure(serverUrl: fixture.url, accessToken: 'access-token');
    expect(await api.downloadFile('file-1', destination), destination);
    expect(await File(destination).readAsBytes(), fixture.audioBytes);
    expect(fixture.rangeRequestSeen, isTrue);
    expect(await api.shareFile('file-1'), '${fixture.url}/shared/audio');
  });

  test('يستأنف حالة المهمة ويلغيها من API', () async {
    final fixture = await _MobileApiFixture.start();
    addTearDown(fixture.close);
    final api = ApiService()..configure(serverUrl: fixture.url, accessToken: 'access-token');
    expect((await api.job('job-1')).status, 'completed');
    expect((await api.cancelJob('job-1')).status, 'cancelled');
  });

  test('مصدر التطبيق لا يحتوي مفاتيح API مدمجة', () async {
    final secretPattern = RegExp(r'(?:AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{20,})');
    final files = Directory('lib').listSync(recursive: true).whereType<File>().where((file) => file.path.endsWith('.dart'));
    for (final file in files) {
      expect(secretPattern.hasMatch(await file.readAsString()), isFalse, reason: file.path);
    }
  });
}
