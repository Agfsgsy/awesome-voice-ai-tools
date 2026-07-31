import 'dart:io';

import 'package:ffmpeg_kit_flutter_new_audio/ffmpeg_kit.dart';
import 'package:ffmpeg_kit_flutter_new_audio/ffprobe_kit.dart';
import 'package:ffmpeg_kit_flutter_new_audio/return_code.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';

class LocalAudioService {
  Future<AudioAnalysis> analyze(String path) async {
    if (!await File(path).exists()) throw const AppException('الملف المحدد غير موجود.');
    final informationSession = await FFprobeKit.getMediaInformation(path);
    final information = informationSession.getMediaInformation();
    if (information == null) throw const AppException('صيغة الملف غير قابلة للفك.');
    final duration = double.tryParse(information.getDuration() ?? '') ?? 0;
    final streams = information.getStreams();
    final audioStream = streams.where((stream) => stream.getType() == 'audio').firstOrNull;
    if (duration <= 0 || audioStream == null) throw const AppException('الملف لا يحتوي صوتًا صالحًا.');

    final command = '-hide_banner -i ${_quote(path)} -af '
        '"silencedetect=noise=-45dB:d=0.20,astats=metadata=1:reset=0" -f null -';
    final session = await FFmpegKit.execute(command);
    final returnCode = await session.getReturnCode();
    final output = await session.getOutput() ?? '';
    if (!ReturnCode.isSuccess(returnCode)) throw const AppException('صيغة الملف غير قابلة للفك.');

    final sampleRate = int.tryParse(audioStream.getSampleRate() ?? '') ?? 0;
    final rms = _lastNumber(output, RegExp(r'RMS level dB:\s*(-?[0-9.]+)')) ?? -90;
    final peak = _lastNumber(output, RegExp(r'Peak level dB:\s*(-?[0-9.]+)')) ?? -90;
    final silenceDuration = RegExp(r'silence_duration:\s*([0-9.]+)')
        .allMatches(output)
        .fold<double>(0, (sum, match) => sum + (double.tryParse(match.group(1) ?? '') ?? 0));
    final silencePercent = (silenceDuration / duration * 100).clamp(0, 100).toDouble();
    final clippingPercent = peak >= -0.1 ? 1.0 : 0.0;
    final noiseFloor = (rms - 18).clamp(-96, 0).toDouble();
    final sampleScore = sampleRate >= 24000 ? 100 : (sampleRate >= 16000 ? 80 : 45);
    final score = (100 - silencePercent * 0.4 - clippingPercent * 20 + sampleScore * 0.2).round().clamp(0, 100);
    final clear = duration >= 2 && silencePercent < 85 && rms > -55;
    final issues = <String>[
      if (!clear) 'التسجيل لا يحتوي كلامًا واضحًا',
      if (silencePercent > 65) 'نسبة الصمت مرتفعة',
      if (clippingPercent > 0) 'يوجد تشويه أو قص في قمم الصوت',
      if (sampleRate < 16000) 'جودة العينة منخفضة',
    ];
    return AudioAnalysis(
      durationSeconds: duration,
      noiseFloorDbfs: noiseFloor,
      silencePercent: silencePercent,
      clippingPercent: clippingPercent,
      sampleRate: sampleRate,
      sampleQuality: sampleRate >= 24000 ? 'ممتازة' : (sampleRate >= 16000 ? 'جيدة' : 'منخفضة'),
      distortion: clippingPercent > 0 ? 'ملحوظ' : 'منخفض',
      qualityScore: score,
      clearSpeech: clear,
      issues: issues,
      recommendation: clear ? 'التسجيل مناسب للرفع والتحليل الدقيق على الخادم' : 'أعد التسجيل في مكان أهدأ وعلى بعد ثابت من الميكروفون',
    );
  }

  Future<String> convertToWav(String inputPath) async {
    final cache = await getTemporaryDirectory();
    final output = p.join(cache.path, '${p.basenameWithoutExtension(inputPath)}_${DateTime.now().millisecondsSinceEpoch}.wav');
    final session = await FFmpegKit.execute(
      '-y -i ${_quote(inputPath)} -vn -ac 1 -ar 24000 -c:a pcm_s16le ${_quote(output)}',
    );
    final code = await session.getReturnCode();
    if (!ReturnCode.isSuccess(code) || !await File(output).exists() || await File(output).length() <= 44) {
      throw const AppException('فشل تحويل الملف إلى WAV.');
    }
    return output;
  }

  double? _lastNumber(String text, RegExp pattern) {
    final matches = pattern.allMatches(text).toList();
    return matches.isEmpty ? null : double.tryParse(matches.last.group(1) ?? '');
  }

  String _quote(String value) => "'${value.replaceAll("'", "'\\''")}'";
}

extension _FirstOrNull<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
