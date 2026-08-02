import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';

enum RecorderState { idle, recording, paused, stopped }

class AudioRecorderService {
  AudioRecorderService({AudioRecorder? recorder}) : _recorder = recorder;

  AudioRecorder? _recorder;
  RecorderState _state = RecorderState.idle;
  String? _path;

  AudioRecorder get _activeRecorder => _recorder ??= AudioRecorder();

  RecorderState get state => _state;
  String? get path => _path;

  Future<String> start() async {
    var permission = await Permission.microphone.status;
    if (!permission.isGranted) permission = await Permission.microphone.request();
    if (!permission.isGranted) {
      throw const AppException('يلزم السماح باستخدام الميكروفون لبدء التسجيل.');
    }
    if (!await _activeRecorder.hasPermission()) {
      throw const AppException('تعذر الوصول إلى الميكروفون. راجع أذونات التطبيق.');
    }
    final directory = await getApplicationDocumentsDirectory();
    final recordings = Directory(p.join(directory.path, 'recordings'));
    await recordings.create(recursive: true);
    _path = p.join(recordings.path, 'recording_${DateTime.now().millisecondsSinceEpoch}.wav');
    await _activeRecorder.start(
      const RecordConfig(
        encoder: AudioEncoder.wav,
        bitRate: 256000,
        sampleRate: 48000,
        numChannels: 1,
        autoGain: true,
        echoCancel: true,
        noiseSuppress: true,
      ),
      path: _path!,
    );
    _state = RecorderState.recording;
    return _path!;
  }

  Future<void> pause() async {
    if (_state != RecorderState.recording) return;
    await _activeRecorder.pause();
    _state = RecorderState.paused;
  }

  Future<void> resume() async {
    if (_state != RecorderState.paused) return;
    await _activeRecorder.resume();
    _state = RecorderState.recording;
  }

  Future<String?> stop() async {
    if (_state != RecorderState.recording && _state != RecorderState.paused) return _path;
    final result = await _activeRecorder.stop();
    _path = result ?? _path;
    _state = RecorderState.stopped;
    if (_path == null || !await File(_path!).exists() || await File(_path!).length() <= 44) {
      throw const AppException('التسجيل الناتج غير صالح.');
    }
    return _path;
  }

  Future<void> delete() async {
    if (_state == RecorderState.recording || _state == RecorderState.paused) await _activeRecorder.cancel();
    final current = _path;
    if (current != null) {
      final file = File(current);
      if (await file.exists()) await file.delete();
    }
    _path = null;
    _state = RecorderState.idle;
  }

  Future<void> dispose() async {
    final recorder = _recorder;
    if (recorder != null) await recorder.dispose();
  }
}
