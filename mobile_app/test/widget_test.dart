import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_ai_mobile/app/app.dart';
import 'package:voice_ai_mobile/app/router.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/features/recorder/recorder_screen.dart';
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

  @override
  Future<void> dispose() async {}
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

  @override
  Future<void> dispose() async {}
}

List<Override> _overrides({
  _FakeRecorder? recorder,
  _FakePicker? picker,
  _FakePlayer? player,
}) => <Override>[
  appControllerProvider.overrideWith(
    (ref) =>
        _TestAppController(const AppState(initialized: true, localMode: true)),
  ),
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

void _usePhoneViewport(WidgetTester tester) {
  tester.view
    ..physicalSize = const Size(390, 844)
    ..devicePixelRatio = 1;
  addTearDown(() {
    tester.view
      ..resetPhysicalSize()
      ..resetDevicePixelRatio();
  });
}

Widget _recorderHarness(List<Override> overrides) => ProviderScope(
  overrides: overrides,
  child: const MaterialApp(
    home: Directionality(
      textDirection: TextDirection.rtl,
      child: RecorderScreen(),
    ),
  ),
);

void _deleteDirectory(Directory directory) {
  if (directory.existsSync()) directory.deleteSync(recursive: true);
}

void main() {
  testWidgets('يشغّل التطبيق بالعربية RTL ويتنقل بين الصفحات', (tester) async {
    _usePhoneViewport(tester);
    appRouter.go('/splash');
    await tester.pumpWidget(
      ProviderScope(overrides: _overrides(), child: const VoiceAiMobileApp()),
    );
    await _pumpUntilVisible(tester, find.text('لوحة التحكم'));

    expect(find.text('لوحة التحكم'), findsWidgets);
    final directionality = tester.widget<Directionality>(
      find.byType(Directionality).first,
    );
    expect(directionality.textDirection, TextDirection.rtl);

    await tester.tap(find.text('الاستوديو').last);
    await _pumpUntilVisible(tester, find.text('توليد الصوت (Voice Studio)'));
    expect(find.text('توليد الصوت (Voice Studio)'), findsOneWidget);
    expect(find.text('محرك الهاتف — دون إنترنت'), findsOneWidget);
    expect(find.text('إنشاء الصوت على الهاتف'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  });

  testWidgets('يسجل ويوقف مؤقتًا ويستكمل ويحلل ويشغل التسجيل', (tester) async {
    _usePhoneViewport(tester);
    final directory = Directory.systemTemp.createTempSync(
      'voice_ai_recorder_test',
    );
    final file = File('${directory.path}/recorded.wav');
    file.writeAsBytesSync(List<int>.filled(128, 1));
    final recorder = _FakeRecorder(file.path);
    final player = _FakePlayer();
    addTearDown(() => _deleteDirectory(directory));

    await tester.pumpWidget(
      _recorderHarness(
        _overrides(
          recorder: recorder,
          picker: _FakePicker(file.path),
          player: player,
        ),
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
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    _deleteDirectory(directory);
  });

  testWidgets('يختار ملفًا من مدير الملفات ويعرض نتيجة التحليل', (
    tester,
  ) async {
    _usePhoneViewport(tester);
    final directory = Directory.systemTemp.createTempSync(
      'voice_ai_picker_test',
    );
    final file = File('${directory.path}/picked.mp3');
    file.writeAsBytesSync(List<int>.filled(256, 2));
    addTearDown(() => _deleteDirectory(directory));

    await tester.pumpWidget(
      _recorderHarness(_overrides(picker: _FakePicker(file.path))),
    );
    await _pumpUntilVisible(tester, find.text('اختيار ملف'));
    await tester.tap(find.text('اختيار ملف'));
    await _pumpUntilVisible(tester, find.text('picked.mp3'));
    expect(find.text('picked.mp3'), findsOneWidget);
    expect(find.text('تحليل جودة التسجيل'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    _deleteDirectory(directory);
  });
}
