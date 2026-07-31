import 'dart:async';

import 'package:just_audio/just_audio.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';

class AudioPlayerService {
  AudioPlayerService({AudioPlayer? player}) : _player = player ?? AudioPlayer();

  final AudioPlayer _player;

  Stream<PlayerState> get playerState => _player.playerStateStream;
  Stream<Duration> get position => _player.positionStream;
  Stream<Duration?> get duration => _player.durationStream;

  Future<void> playFile(String path) async {
    try {
      await _player.setFilePath(path);
      await _player.play();
    } on PlayerException catch (error) {
      throw AppException('تعذر تشغيل الصوت: ${error.message}');
    }
  }

  Future<void> pause() => _player.pause();
  Future<void> resume() => _player.play();
  Future<void> stop() => _player.stop();
  Future<void> seek(Duration position) => _player.seek(position);
  Future<void> dispose() => _player.dispose();
}
