import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/services/cloud_provider_service.dart';

class _CloudFixture {
  _CloudFixture._(this.server) {
    serving = _serve();
  }

  final HttpServer server;
  late final Future<void> serving;
  bool sawGeminiKey = false;
  bool sawElevenLabsKey = false;
  bool sawCloneUpload = false;
  bool sawResumableUpload = false;
  bool deletedGeminiFile = false;

  String get url => 'http://${server.address.address}:${server.port}';

  static Future<_CloudFixture> start() async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    return _CloudFixture._(server);
  }

  Future<void> _serve() async {
    await for (final request in server) {
      await _handle(request);
    }
  }

  Future<void> _handle(HttpRequest request) async {
    final geminiKey = request.headers.value('x-goog-api-key');
    final elevenLabsKey = request.headers.value('xi-api-key');
    sawGeminiKey |= geminiKey == 'gemini-test-key';
    sawElevenLabsKey |= elevenLabsKey == 'eleven-test-key';
    if (geminiKey == 'invalid' || elevenLabsKey == 'invalid') {
      await _json(request.response, HttpStatus.unauthorized, <String, Object>{
        'error': <String, String>{'message': 'invalid key'},
      });
      return;
    }

    final path = request.uri.path;
    if (path == '/upload/v1beta/files') {
      await request.drain<void>();
      request.response.headers.set(
        'x-goog-upload-url',
        '$url/upload-session',
      );
      await _json(request.response, HttpStatus.ok, const <String, Object>{});
      return;
    }
    if (path == '/upload-session') {
      await request.drain<void>();
      sawResumableUpload = true;
      await _json(request.response, HttpStatus.ok, <String, Object>{
        'file': <String, String>{
          'name': 'files/test-audio',
          'uri': 'https://files.example/test-audio',
          'mimeType': 'audio/wav',
          'state': 'ACTIVE',
        },
      });
      return;
    }
    if (path == '/v1beta/files/test-audio' && request.method == 'DELETE') {
      deletedGeminiFile = true;
      await _json(request.response, HttpStatus.ok, const <String, Object>{});
      return;
    }
    if (path.startsWith('/v1beta/models/')) {
      await _json(request.response, HttpStatus.ok, <String, String>{
        'name': 'models/gemini-3.1-flash-tts-preview',
      });
      return;
    }
    if (path == '/v1/user/subscription') {
      await _json(request.response, HttpStatus.ok, <String, Object>{
        'status': 'active',
        'tier': 'creator',
        'character_count': 100,
        'character_limit': 1000,
        'can_use_instant_voice_cloning': true,
      });
      return;
    }
    if (path == '/v2/voices') {
      await _json(request.response, HttpStatus.ok, <String, Object>{
        'voices': <Map<String, String>>[
          <String, String>{
            'voice_id': 'voice-1',
            'name': 'صوت الاختبار',
            'category': 'cloned',
          },
        ],
      });
      return;
    }
    if (path == '/v1/voices/add') {
      final body = await request.fold<List<int>>(
        <int>[],
        (bytes, chunk) => bytes..addAll(chunk),
      );
      sawCloneUpload =
          utf8.decode(body, allowMalformed: true).contains('صوت الاختبار');
      await _json(request.response, HttpStatus.ok, <String, Object>{
        'voice_id': 'cloned-voice-1',
        'requires_verification': false,
      });
      return;
    }
    if (path.startsWith('/v1/text-to-speech/')) {
      await request.drain<void>();
      final bytes = <int>[0x49, 0x44, 0x33, ...List<int>.filled(253, 7)];
      request.response
        ..statusCode = HttpStatus.ok
        ..headers.contentType = ContentType('audio', 'mpeg')
        ..contentLength = bytes.length
        ..add(bytes);
      await request.response.close();
      return;
    }
    if (path.startsWith('/v1/speech-to-speech/')) {
      await request.drain<void>();
      final bytes = <int>[0x49, 0x44, 0x33, ...List<int>.filled(253, 9)];
      request.response
        ..statusCode = HttpStatus.ok
        ..headers.contentType = ContentType('audio', 'mpeg')
        ..contentLength = bytes.length
        ..add(bytes);
      await request.response.close();
      return;
    }
    if (path == '/v1beta/interactions') {
      final body = await utf8.decoder.bind(request).join();
      if (body.contains('response_format')) {
        await _json(request.response, HttpStatus.ok, <String, Object>{
          'steps': <Map<String, Object>>[
            <String, Object>{
              'content': <Map<String, Object>>[
                <String, Object>{
                  'type': 'audio',
                  'data': base64Encode(List<int>.filled(256, 3)),
                  'mime_type': 'audio/l16',
                  'sample_rate': 24000,
                },
              ],
            },
          ],
        });
      } else {
        await _json(request.response, HttpStatus.ok, <String, String>{
          'output_text': '00:00 هذا نص عربي مستخرج من التسجيل.',
        });
      }
      return;
    }
    await _json(request.response, HttpStatus.notFound, <String, String>{
      'message': 'not found',
    });
  }

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
  test('يفحص Gemini وElevenLabs ويعرض الأصوات والحصة', () async {
    final fixture = await _CloudFixture.start();
    final directory = await Directory.systemTemp.createTemp('cloud-status');
    addTearDown(() async {
      await fixture.close();
      await directory.delete(recursive: true);
    });
    final service = CloudProviderService(
      geminiBaseUrl: fixture.url,
      elevenLabsBaseUrl: fixture.url,
      outputDirectory: () async => directory,
    );

    final gemini = await service.checkGemini(
      apiKey: 'gemini-test-key',
      model: 'gemini-3.1-flash-tts-preview',
    );
    final eleven = await service.checkElevenLabs(apiKey: 'eleven-test-key');
    final voices = await service.listElevenLabsVoices(
      apiKey: 'eleven-test-key',
    );

    expect(gemini.available, isTrue);
    expect(eleven.remainingCharacters, 900);
    expect(eleven.canCloneVoice, isTrue);
    expect(voices.single.id, 'voice-1');
    expect(fixture.sawGeminiKey, isTrue);
    expect(fixture.sawElevenLabsKey, isTrue);
  });

  test('يولّد Gemini WAV وElevenLabs MP3 ويحفظهما محليًا', () async {
    final fixture = await _CloudFixture.start();
    final directory = await Directory.systemTemp.createTemp('cloud-audio');
    addTearDown(() async {
      await fixture.close();
      await directory.delete(recursive: true);
    });
    final service = CloudProviderService(
      geminiBaseUrl: fixture.url,
      elevenLabsBaseUrl: fixture.url,
      outputDirectory: () async => directory,
    );

    final geminiPath = await service.synthesizeGemini(
      apiKey: 'gemini-test-key',
      model: 'gemini-3.1-flash-tts-preview',
      voice: 'Kore',
      text: 'اختبار صوت عربي',
    );
    final elevenPath = await service.synthesizeElevenLabs(
      apiKey: 'eleven-test-key',
      model: 'eleven_multilingual_v2',
      voiceId: 'voice-1',
      text: 'اختبار صوت عربي',
    );

    final geminiBytes = await File(geminiPath).readAsBytes();
    expect(ascii.decode(geminiBytes.take(4).toList()), 'RIFF');
    expect(await File(elevenPath).length(), greaterThan(128));
  });

  test('يستنسخ صوت ElevenLabs بعد رفع المرجع', () async {
    final fixture = await _CloudFixture.start();
    final directory = await Directory.systemTemp.createTemp('cloud-clone');
    addTearDown(() async {
      await fixture.close();
      await directory.delete(recursive: true);
    });
    final reference = File('${directory.path}/reference.wav');
    await reference.writeAsBytes(<int>[
      ...ascii.encode('RIFF'),
      ...List<int>.filled(256, 1),
    ]);
    final service = CloudProviderService(
      geminiBaseUrl: fixture.url,
      elevenLabsBaseUrl: fixture.url,
      outputDirectory: () async => directory,
    );

    final voice = await service.cloneElevenLabsVoice(
      apiKey: 'eleven-test-key',
      referencePath: reference.path,
      voiceName: 'صوت الاختبار',
      rights: 'self',
    );

    expect(voice.id, 'cloned-voice-1');
    expect(fixture.sawCloneUpload, isTrue);
  });

  test('يغيّر صوت التسجيل عبر ElevenLabs ويحفظ النتيجة', () async {
    final fixture = await _CloudFixture.start();
    final directory = await Directory.systemTemp.createTemp('cloud-change');
    addTearDown(() async {
      await fixture.close();
      await directory.delete(recursive: true);
    });
    final source = File('${directory.path}/source.wav');
    await source.writeAsBytes(<int>[
      ...ascii.encode('RIFF'),
      ...List<int>.filled(256, 1),
    ]);
    final service = CloudProviderService(
      geminiBaseUrl: fixture.url,
      elevenLabsBaseUrl: fixture.url,
      outputDirectory: () async => directory,
    );

    final output = await service.changeVoiceElevenLabs(
      apiKey: 'eleven-test-key',
      model: 'eleven_multilingual_sts_v2',
      voiceId: 'voice-1',
      sourcePath: source.path,
      removeBackgroundNoise: true,
    );

    expect(await File(output).length(), greaterThan(128));
    expect(fixture.sawElevenLabsKey, isTrue);
  });

  test('يحوّل تسجيلًا صغيرًا إلى نص عربي عبر Gemini', () async {
    final fixture = await _CloudFixture.start();
    final directory = await Directory.systemTemp.createTemp('cloud-stt');
    addTearDown(() async {
      await fixture.close();
      await directory.delete(recursive: true);
    });
    final audio = File('${directory.path}/speech.wav');
    await audio.writeAsBytes(<int>[
      ...ascii.encode('RIFF'),
      ...List<int>.filled(512, 2),
    ]);
    final service = CloudProviderService(
      geminiBaseUrl: fixture.url,
      elevenLabsBaseUrl: fixture.url,
      outputDirectory: () async => directory,
    );

    final transcript = await service.transcribeGemini(
      apiKey: 'gemini-test-key',
      model: 'gemini-3.6-flash',
      audioPath: audio.path,
    );

    expect(transcript, contains('نص عربي'));
  });

  test('يرفع التسجيل الكبير إلى Gemini باستئناف ثم يحذف النسخة المؤقتة',
      () async {
    final fixture = await _CloudFixture.start();
    final directory = await Directory.systemTemp.createTemp('cloud-large-stt');
    addTearDown(() async {
      await fixture.close();
      await directory.delete(recursive: true);
    });
    final audio = File('${directory.path}/large.wav');
    final writer = await audio.open(mode: FileMode.write);
    await writer.writeFrom(ascii.encode('RIFF'));
    await writer.truncate(14 * 1024 * 1024 + 128);
    await writer.close();
    final service = CloudProviderService(
      geminiBaseUrl: fixture.url,
      elevenLabsBaseUrl: fixture.url,
      outputDirectory: () async => directory,
    );

    final transcript = await service.transcribeGemini(
      apiKey: 'gemini-test-key',
      model: 'gemini-3.6-flash',
      audioPath: audio.path,
    );

    expect(transcript, contains('نص عربي'));
    expect(fixture.sawResumableUpload, isTrue);
    expect(fixture.deletedGeminiFile, isTrue);
  });

  test('يرفض المفتاح غير الصالح برسالة عربية دون كشفه', () async {
    final fixture = await _CloudFixture.start();
    final directory = await Directory.systemTemp.createTemp('cloud-auth');
    addTearDown(() async {
      await fixture.close();
      await directory.delete(recursive: true);
    });
    final service = CloudProviderService(
      geminiBaseUrl: fixture.url,
      elevenLabsBaseUrl: fixture.url,
      outputDirectory: () async => directory,
    );

    await expectLater(
      service.checkGemini(apiKey: 'invalid', model: 'model'),
      throwsA(
        isA<AppException>().having(
          (error) => error.message,
          'message',
          contains('مفتاح Gemini غير صالح'),
        ),
      ),
    );
  });
}
