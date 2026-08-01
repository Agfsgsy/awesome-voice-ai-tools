import 'dart:async';
import 'dart:io';

import 'package:ffmpeg_kit_flutter_new_audio/ffmpeg_kit.dart';
import 'package:ffmpeg_kit_flutter_new_audio/return_code.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';

class LocalTtsStatus {
  const LocalTtsStatus({
    required this.available,
    required this.installed,
    this.language,
    this.engine,
    this.message,
  });

  final bool available;
  final bool installed;
  final String? language;
  final String? engine;
  final String? message;
}

class LocalTtsService {
  LocalTtsService({FlutterTts? flutterTts}) : _tts = flutterTts ?? FlutterTts();

  static const _systemChannel = MethodChannel('voice_ai_mobile/system');
  final FlutterTts _tts;

  Future<LocalTtsStatus> status() async {
    try {
      final language = await _findArabicLanguage(requireInstalled: false);
      final installedLanguage = await _findArabicLanguage(
        requireInstalled: true,
      );
      final Object? rawEngine = Platform.isAndroid
          ? await _tts.getDefaultEngine
          : 'system';
      final engine = rawEngine?.toString();
      if (language == null) {
        return LocalTtsStatus(
          available: false,
          installed: false,
          engine: engine,
          message:
              'لا يوجد محرك صوت عربي على الهاتف. اضغط «تنزيل الصوت العربي».',
        );
      }
      return LocalTtsStatus(
        available: true,
        installed: installedLanguage != null,
        language: installedLanguage ?? language,
        engine: engine,
        message: installedLanguage == null
            ? 'الصوت العربي متاح لكنه غير مُنزّل للعمل دون إنترنت.'
            : 'الصوت العربي المحلي جاهز للعمل دون خادم.',
      );
    } on Object {
      return const LocalTtsStatus(
        available: false,
        installed: false,
        message:
            'تعذر تشغيل محرك الصوت في النظام. افتح إعدادات الصوت وثبّت العربية.',
      );
    }
  }

  Future<String> synthesizeToFile(String text, {double speed = 1}) async {
    final cleanText = text.trim();
    if (cleanText.isEmpty)
      throw const AppException('أدخل نصًا واضحًا لتحويله إلى صوت.');
    final language = await _findArabicLanguage(
      requireInstalled: Platform.isAndroid,
    );
    if (language == null) {
      throw const AppException(
        'الصوت العربي غير مثبت على الهاتف. افتح الإعدادات واضغط «تنزيل الصوت العربي» أولًا.',
      );
    }

    final languageResult = await _tts.setLanguage(language);
    if (!_succeeded(languageResult))
      throw const AppException('تعذر تفعيل اللغة العربية في محرك صوت الهاتف.');
    await _selectOfflineVoice(language);
    await _tts.setVolume(1);
    await _tts.setPitch(1);
    await _tts.setSpeechRate((speed * 0.5).clamp(0.25, 1).toDouble());
    await _tts.awaitSynthCompletion(true);

    final maximum = Platform.isAndroid
        ? await _tts.getMaxSpeechInputLength
        : null;
    final chunks = _splitText(
      cleanText,
      maximum == null ? 2800 : (maximum - 200).clamp(500, 3500),
    );
    final documents = await getApplicationDocumentsDirectory();
    final outputDirectory = Directory(
      p.join(documents.path, 'voice_ai_outputs'),
    );
    await outputDirectory.create(recursive: true);
    final stamp = DateTime.now().millisecondsSinceEpoch;
    final output = p.join(outputDirectory.path, 'voice_ai_local_$stamp.wav');

    if (chunks.length == 1) {
      await _synthesizeChunk(chunks.single, output);
      return output;
    }

    final temporary = await getTemporaryDirectory();
    final workDirectory = Directory(
      p.join(temporary.path, 'voice_ai_tts_$stamp'),
    );
    await workDirectory.create(recursive: true);
    try {
      final chunkFiles = <String>[];
      for (var index = 0; index < chunks.length; index++) {
        final chunkPath = p.join(workDirectory.path, 'chunk_$index.wav');
        await _synthesizeChunk(chunks[index], chunkPath);
        chunkFiles.add(chunkPath);
      }
      final concatFile = File(p.join(workDirectory.path, 'concat.txt'));
      await concatFile.writeAsString(
        chunkFiles
            .map((path) => "file '${path.replaceAll("'", "'\\''")}'")
            .join('\n'),
        flush: true,
      );
      final session = await FFmpegKit.execute(
        '-y -f concat -safe 0 -i ${_quote(concatFile.path)} -vn -ac 1 -ar 24000 -c:a pcm_s16le ${_quote(output)}',
      );
      final code = await session.getReturnCode();
      if (!ReturnCode.isSuccess(code) || !await _validAudioFile(output)) {
        throw const AppException('تعذر دمج أجزاء المستند في ملف صوتي صالح.');
      }
      return output;
    } finally {
      if (await workDirectory.exists())
        await workDirectory.delete(recursive: true);
    }
  }

  Future<void> installVoiceData() async {
    try {
      await _systemChannel.invokeMethod<void>('installTtsData');
    } on PlatformException {
      await openSystemSettings();
    }
  }

  Future<void> openSystemSettings() =>
      _systemChannel.invokeMethod<void>('openTtsSettings');

  Future<void> stop() async => _tts.stop();

  void dispose() => unawaited(_tts.stop());

  Future<void> _synthesizeChunk(String text, String output) async {
    final result = await _tts.synthesizeToFile(text, output, true);
    if (!_succeeded(result) || !await _validAudioFile(output)) {
      throw const AppException(
        'الملف الناتج غير صالح. تأكد أن بيانات الصوت العربي مثبتة على الهاتف.',
      );
    }
  }

  Future<bool> _validAudioFile(String path) async {
    final file = File(path);
    return await file.exists() && await file.length() > 44;
  }

  Future<String?> _findArabicLanguage({required bool requireInstalled}) async {
    final raw = await _tts.getLanguages;
    final languages = raw is List<dynamic>
        ? raw
              .map((Object? language) => language.toString())
              .where((language) => language.toLowerCase().startsWith('ar'))
              .toList()
        : <String>[];
    languages.sort(
      (a, b) => _languagePriority(a).compareTo(_languagePriority(b)),
    );
    for (final language in languages) {
      if (!requireInstalled ||
          !Platform.isAndroid ||
          _succeeded(await _tts.isLanguageInstalled(language)))
        return language;
    }
    return null;
  }

  int _languagePriority(String language) {
    final normalized = language.toLowerCase();
    if (normalized == 'ar-sa') return 0;
    if (normalized == 'ar-eg') return 1;
    if (normalized == 'ar') return 2;
    return 3;
  }

  Future<void> _selectOfflineVoice(String language) async {
    if (!Platform.isAndroid) return;
    final raw = await _tts.getVoices;
    if (raw is! List<dynamic>) return;
    for (final item in raw) {
      if (item is! Map<dynamic, dynamic>) continue;
      final locale = (item['locale'] as Object?)?.toString() ?? '';
      final name = (item['name'] as Object?)?.toString() ?? '';
      final networkRequired =
          (item['network_required'] as Object?)?.toString() == '1';
      if (name.isNotEmpty &&
          locale.toLowerCase().startsWith('ar') &&
          !networkRequired) {
        await _tts.setVoice(<String, String>{'name': name, 'locale': locale});
        return;
      }
    }
  }

  List<String> _splitText(String text, int maximum) {
    if (text.length <= maximum) return <String>[text];
    final chunks = <String>[];
    var remaining = text;
    while (remaining.length > maximum) {
      var cut = remaining.lastIndexOf(RegExp(r'[.!؟؛،\n]'), maximum);
      if (cut < maximum ~/ 2) cut = remaining.lastIndexOf(' ', maximum);
      if (cut < maximum ~/ 2) cut = maximum;
      chunks.add(
        remaining
            .substring(
              0,
              cut + (cut < remaining.length && cut != maximum ? 1 : 0),
            )
            .trim(),
      );
      remaining = remaining
          .substring(cut + (cut < remaining.length && cut != maximum ? 1 : 0))
          .trimLeft();
    }
    if (remaining.isNotEmpty) chunks.add(remaining);
    return chunks.where((chunk) => chunk.isNotEmpty).toList();
  }

  bool _succeeded(dynamic value) => value == true || value == 1 || value == '1';

  String _quote(String value) => "'${value.replaceAll("'", "'\\''")}'";
}
