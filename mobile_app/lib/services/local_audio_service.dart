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
    if (!await File(path).exists()) {
      throw const AppException('الملف المحدد غير موجود.');
    }
    final informationSession = await FFprobeKit.getMediaInformation(path);
    final information = informationSession.getMediaInformation();
    if (information == null) {
      throw const AppException('صيغة الملف غير قابلة للفك.');
    }
    final duration = double.tryParse(information.getDuration() ?? '') ?? 0;
    final streams = information.getStreams();
    final audioStream = streams
        .where((stream) => stream.getType() == 'audio')
        .firstOrNull;
    if (duration <= 0 || audioStream == null) {
      throw const AppException('الملف لا يحتوي صوتًا صالحًا.');
    }

    final command =
        '-hide_banner -i ${_quote(path)} -af '
        '"silencedetect=noise=-45dB:d=0.20,astats=metadata=1:reset=0" -f null -';
    final session = await FFmpegKit.execute(command);
    final returnCode = await session.getReturnCode();
    final output = await session.getOutput() ?? '';
    if (!ReturnCode.isSuccess(returnCode)) {
      throw const AppException('صيغة الملف غير قابلة للفك.');
    }

    final sampleRate = int.tryParse(audioStream.getSampleRate() ?? '') ?? 0;
    final rms =
        _lastNumber(output, RegExp(r'RMS level dB:\s*(-?[0-9.]+)')) ?? -90;
    final peak =
        _lastNumber(output, RegExp(r'Peak level dB:\s*(-?[0-9.]+)')) ?? -90;
    final silenceDuration = RegExp(r'silence_duration:\s*([0-9.]+)')
        .allMatches(output)
        .fold<double>(
          0,
          (sum, match) => sum + (double.tryParse(match.group(1) ?? '') ?? 0),
        );
    final silencePercent = (silenceDuration / duration * 100)
        .clamp(0, 100)
        .toDouble();
    final clippingPercent = peak >= -0.1 ? 1.0 : 0.0;
    final noiseFloor = (rms - 18).clamp(-96, 0).toDouble();
    final sampleScore = sampleRate >= 24000
        ? 100
        : (sampleRate >= 16000 ? 80 : 45);
    final score =
        (100 - silencePercent * 0.4 - clippingPercent * 20 + sampleScore * 0.2)
            .round()
            .clamp(0, 100);
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
      sampleQuality: sampleRate >= 24000
          ? 'ممتازة'
          : (sampleRate >= 16000 ? 'جيدة' : 'منخفضة'),
      distortion: clippingPercent > 0 ? 'ملحوظ' : 'منخفض',
      qualityScore: score,
      clearSpeech: clear,
      issues: issues,
      recommendation: clear
          ? 'التسجيل مناسب للرفع والتحليل الدقيق على الخادم'
          : 'أعد التسجيل في مكان أهدأ وعلى بعد ثابت من الميكروفون',
    );
  }

  Future<String> convertToWav(String inputPath) async {
    final cache = await getTemporaryDirectory();
    final output = p.join(
      cache.path,
      '${p.basenameWithoutExtension(inputPath)}_${DateTime.now().millisecondsSinceEpoch}.wav',
    );
    final session = await FFmpegKit.execute(
      '-y -i ${_quote(inputPath)} -vn -ac 1 -ar 24000 -c:a pcm_s16le ${_quote(output)}',
    );
    final code = await session.getReturnCode();
    if (!ReturnCode.isSuccess(code) ||
        !await File(output).exists() ||
        await File(output).length() <= 44) {
      throw const AppException('فشل تحويل الملف إلى WAV.');
    }
    return output;
  }

  Future<String> applyEffect(String inputPath, String preset) async {
    if (!await File(inputPath).exists()) {
      throw const AppException('الملف الصوتي المحدد غير موجود.');
    }
    final filter = switch (preset) {
      'studio' =>
        'highpass=f=75,lowpass=f=14000,afftdn=nf=-28,dynaudnorm=f=150:g=15',
      'lecture' =>
        'highpass=f=100,lowpass=f=9000,acompressor=threshold=-18dB:ratio=3:attack=20:release=250,loudnorm=I=-18',
      'mosque' =>
        'highpass=f=80,aecho=0.8:0.88:70:0.28,aecho=0.8:0.82:130:0.16,loudnorm=I=-18',
      'deep_voice' =>
        'asetrate=24000*0.890899,aresample=24000,atempo=1.122462,acompressor=threshold=-16dB:ratio=2.5',
      'podcast' =>
        'highpass=f=80,afftdn=nf=-30,acompressor=threshold=-20dB:ratio=4:attack=15:release=220,loudnorm=I=-16',
      'video_commentary' =>
        'highpass=f=90,acompressor=threshold=-18dB:ratio=3.5,equalizer=f=3500:t=q:w=1.2:g=3,loudnorm=I=-15',
      _ => throw const AppException('المؤثر الصوتي المحدد غير معروف.'),
    };
    final output = await _processedOutput('effect_$preset');
    final session = await FFmpegKit.execute(
      '-y -i ${_quote(inputPath)} -af "$filter" -vn -ac 2 -ar 24000 -c:a pcm_s16le ${_quote(output)}',
    );
    final code = await session.getReturnCode();
    if (!ReturnCode.isSuccess(code) ||
        !await File(output).exists() ||
        await File(output).length() <= 44) {
      throw const AppException(
        'تعذر تطبيق المؤثر؛ تأكد أن صيغة الملف قابلة للفك.',
      );
    }
    return output;
  }

  Future<String> trim({
    required String inputPath,
    required double removeStartSeconds,
    required double removeEndSeconds,
  }) async {
    if (!await File(inputPath).exists()) {
      throw const AppException('الملف الصوتي المحدد غير موجود.');
    }
    final information = (await FFprobeKit.getMediaInformation(
      inputPath,
    )).getMediaInformation();
    final duration = double.tryParse(information?.getDuration() ?? '') ?? 0;
    final start = removeStartSeconds.clamp(0, duration).toDouble();
    final end = removeEndSeconds.clamp(0, duration).toDouble();
    final remaining = duration - start - end;
    if (duration <= 0 || remaining < 0.25) {
      throw const AppException(
        'قيم القص تزيل التسجيل كاملًا؛ اترك ربع ثانية على الأقل.',
      );
    }
    final output = await _processedOutput('trimmed');
    final session = await FFmpegKit.execute(
      '-y -ss ${start.toStringAsFixed(3)} -i ${_quote(inputPath)} -t ${remaining.toStringAsFixed(3)} -vn -ac 2 -ar 24000 -c:a pcm_s16le ${_quote(output)}',
    );
    final code = await session.getReturnCode();
    if (!ReturnCode.isSuccess(code) ||
        !await File(output).exists() ||
        await File(output).length() <= 44) {
      throw const AppException('تعذر قص الملف الصوتي محليًا.');
    }
    return output;
  }

  Future<String> _processedOutput(String prefix) async {
    final documents = await getApplicationDocumentsDirectory();
    final directory = Directory(p.join(documents.path, 'voice_ai_outputs'));
    await directory.create(recursive: true);
    return p.join(
      directory.path,
      '${prefix}_${DateTime.now().microsecondsSinceEpoch}.wav',
    );
  }

  Future<String> createSongMix({
    required String vocalPath,
    required String title,
    String? instrumentalPath,
    double tempo = 1,
    double pitchSemitones = 0,
    double reverb = 0.25,
  }) async {
    if (!await File(vocalPath).exists()) {
      throw const AppException('الملف الصوتي المحلي غير موجود.');
    }
    if (instrumentalPath != null && !await File(instrumentalPath).exists()) {
      throw const AppException('المسار الموسيقي المحدد غير موجود.');
    }
    final documents = await getApplicationDocumentsDirectory();
    final directory = Directory(p.join(documents.path, 'voice_ai_outputs'));
    await directory.create(recursive: true);
    final safeTitle = title
        .replaceAll(RegExp(r'[^\u0600-\u06FFa-zA-Z0-9_-]+'), '_')
        .replaceAll(RegExp(r'_+'), '_');
    final output = p.join(
      directory.path,
      '${safeTitle.isEmpty ? 'song' : safeTitle}_${DateTime.now().millisecondsSinceEpoch}.wav',
    );
    final pitchFactor = _powerOfTwo(pitchSemitones / 12);
    final tempoCorrection = tempo / pitchFactor;
    final filters = <String>[
      'asetrate=24000*${pitchFactor.toStringAsFixed(6)}',
      'aresample=24000',
      ..._atempoFilters(tempoCorrection),
      if (reverb > 0.01)
        'aecho=0.8:0.88:60:${(reverb * 0.45).clamp(0.02, 0.45).toStringAsFixed(3)}',
    ];
    final String command;
    if (instrumentalPath == null) {
      command =
          '-y -i ${_quote(vocalPath)} -af "${filters.join(',')}" -vn -ac 2 -ar 24000 -c:a pcm_s16le ${_quote(output)}';
    } else {
      command =
          '-y -i ${_quote(vocalPath)} -stream_loop -1 -i ${_quote(instrumentalPath)} '
          '-filter_complex "[0:a]${filters.join(',')},volume=1.0[v];[1:a]aresample=24000,volume=0.30[m];[v][m]amix=inputs=2:duration=first:dropout_transition=2[out]" '
          '-map "[out]" -vn -ac 2 -ar 24000 -c:a pcm_s16le ${_quote(output)}';
    }
    final session = await FFmpegKit.execute(command);
    final code = await session.getReturnCode();
    if (!ReturnCode.isSuccess(code) ||
        !await File(output).exists() ||
        await File(output).length() <= 44) {
      throw const AppException(
        'تعذر إنشاء المشروع الصوتي المحلي. تأكد أن المسار الموسيقي قابل للفك.',
      );
    }
    return output;
  }

  List<String> _atempoFilters(double value) {
    final filters = <String>[];
    var remaining = value;
    while (remaining < 0.5) {
      filters.add('atempo=0.5');
      remaining /= 0.5;
    }
    while (remaining > 2) {
      filters.add('atempo=2.0');
      remaining /= 2;
    }
    filters.add('atempo=${remaining.clamp(0.5, 2).toStringAsFixed(6)}');
    return filters;
  }

  double _powerOfTwo(double exponent) {
    const values = <double>[
      0.7071067812,
      0.7491535384,
      0.7937005260,
      0.8408964153,
      0.8908987181,
      0.9438743127,
      1,
      1.0594630944,
      1.1224620483,
      1.1892071150,
      1.2599210499,
      1.3348398542,
      1.4142135624,
    ];
    final semitone = (exponent * 12).round().clamp(-6, 6);
    return values[semitone + 6];
  }

  double? _lastNumber(String text, RegExp pattern) {
    final matches = pattern.allMatches(text).toList();
    return matches.isEmpty
        ? null
        : double.tryParse(matches.last.group(1) ?? '');
  }

  String _quote(String value) => "'${value.replaceAll("'", "'\\''")}'";
}

extension _FirstOrNull<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
