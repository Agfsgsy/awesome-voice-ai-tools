import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_ai_mobile/app/app.dart';
import 'package:voice_ai_mobile/app/router.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/services/api_service.dart';
import 'package:voice_ai_mobile/services/audio_player_service.dart';
import 'package:voice_ai_mobile/services/audio_recorder_service.dart';
import 'package:voice_ai_mobile/services/document_picker_service.dart';
import 'package:voice_ai_mobile/services/local_audio_service.dart';
import 'package:voice_ai_mobile/services/notification_service.dart';
import 'package:voice_ai_mobile/services/secure_storage_service.dart';

class _TestAppController extends AppController {
  _TestAppController(AppState initial)
      : super(
          SecureStorageService(),
          ApiService(),
          Connectivity(),
          NotificationService(),
          autoInitialize: false,
        ) {
    state = initial;
  }
}

class _FakeRecorder extends AudioRecorderService {
  _FakeRecorder(this.fakePath);

  final String fakePath;
  bool paused = false;

  @override
  Future<String> start() async => fakePath;

  @override
  Future<void> pause() async => paused = true;

  @override
  Future<void> resume() async => paused = false;

  @override
  Future<String?> stop() async => fakePath;

  @override
  Future<void> delete() async {}
}

class _FakePicker extends DocumentPickerService {
  _FakePicker(this.fakePath);

  final String fakePath;

  @override
  Future<String?> pickAny() async => fakePath;
}

class _FakeLocalAudio extends LocalAudioService {
  @override
  Future<AudioAnalysis> analyze(String path) async => const AudioAnalysis(
        durationSeconds: 4.2,
        noiseFloorDbfs: -52,
        silencePercent: 8,
        clippingPercent: 0,
        sampleRate: 48000,
        sampleQuality: 'ممتازة',
        distortion: 'منخفض',
        qualityScore: 91,
        clearSpeech: true,
        issues: <String>[],
        recommendation: 'التسجيل مناسب للاستنساخ',
      );
}

class _FakePlayer extends AudioPlayerService {
  bool played = false;

  @override
  Future<void> playFile(String path) async => played = true;
}

List<Override> _overrides({_FakeRecorder? recorder, _FakePicker? picker, _FakePlayer? player}) => <Override>[
      appControllerProvider.overrideWith((ref) => _TestAppController(const AppState(initialized: true, localMode: true))),
      if (recorder != null) recorderServiceProvider.overrideWithValue(recorder),
      if (picker != null) documentPickerProvider.overrideWithValue(picker),
      if (player != null) playerServiceProvider.overrideWithValue(player),
      localAudioServiceProvider.overrideWithValue(_FakeLocalAudio()),
    ];

Future<void> _pumpUntilVisible(WidgetTester tester, Finder finder) async {
  for (var attempt = 0; attempt < 50; attempt++) {
    await tester.pump(const Duration(milliseconds: 100));
    if (finder.evaluate().isNotEmpty) return;
  }
  fail('لم يظهر العنصر المطلوب خلال خمس ثوانٍ: $finder');
}

void main() {
  testWidgets('يشغّل التطبيق بالعربية RTL ويتنقل بين الصفحات', (tester) async {
    appRouter.go('/splash');
    await tester.pumpWidget(ProviderScope(overrides: _overrides(), child: const VoiceAiMobileApp()));
    await _pumpUntilVisible(tester, find.text('لوحة التحكم'));

    expect(find.text('لوحة التحكم'), findsWidgets);
    final directionality = tester.widget<Directionality>(find.byType(Directionality).first);
    expect(directionality.textDirection, TextDirection.rtl);

    await tester.tap(find.text('الاستوديو').last);
    await _pumpUntilVisible(tester, find.text('توليد الصوت (Voice Studio)'));
    expect(find.text('توليد الصوت (Voice Studio)'), findsOneWidget);
  });

  testWidgets('يسجل ويوقف مؤقتًا ويستكمل ويحلل ويشغل التسجيل', (tester) async {
    final directory = await Directory.systemTemp.createTemp('voice_ai_recorder_test');
    final file = File('${directory.path}/recorded.wav');
    await file.writeAsBytes(List<int>.filled(128, 1));
    final recorder = _FakeRecorder(file.path);
    final player = _FakePlayer();
    addTearDown(() => directory.delete(recursive: true));

    appRouter.go('/record');
    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(recorder: recorder, picker: _FakePicker(file.path), player: player),
        child: const VoiceAiMobileApp(),
      ),
    );
    await _pumpUntilVisible(tester, find.text('بدء التسجيل'));
    await tester.tap(find.text('بدء التسجيل'));
    await tester.pump();
    expect(find.text('إيقاف مؤقت'), findsOneWidget);
    await tester.tap(find.text('إيقاف مؤقت'));
    await tester.pump();
    expect(find.text('استكمال'), findsOneWidget);
    await tester.tap(find.text('استكمال'));
    await tester.pump();
    await tester.tap(find.text('إنهاء التسجيل'));
    await _pumpUntilVisible(tester, find.text('تحليل جودة التسجيل'));
    expect(find.text('تحليل جودة التسجيل'), findsOneWidget);
    expect(find.textContaining('91'), findsWidgets);
    await tester.tap(find.text('معاينة'));
    await tester.pump();
    expect(player.played, isTrue);
  });

  testWidgets('يختار ملفًا من مدير الملفات ويعرض نتيجة التحليل', (tester) async {
    final directory = await Directory.systemTemp.createTemp('voice_ai_picker_test');
    final file = File('${directory.path}/picked.mp3');
    await file.writeAsBytes(List<int>.filled(256, 2));
    addTearDown(() => directory.delete(recursive: true));

    appRouter.go('/record');
    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(picker: _FakePicker(file.path)),
        child: const VoiceAiMobileApp(),
      ),
    );
    await _pumpUntilVisible(tester, find.text('اختيار ملف'));
    await tester.tap(find.text('اختيار ملف'));
    await _pumpUntilVisible(tester, find.text('picked.mp3'));
    expect(find.text('picked.mp3'), findsOneWidget);
    expect(find.text('تحليل جودة التسجيل'), findsOneWidget);
  });
}
