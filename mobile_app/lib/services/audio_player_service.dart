import 'dart:async';

import 'package:just_audio/just_audio.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';

class AudioPlayerService {
  AudioPlayerService({AudioPlayer? player}) : _player = player;

  AudioPlayer? _player;

  AudioPlayer get _activePlayer => _player ??= AudioPlayer();

  Stream<PlayerState> get playerState => _activePlayer.playerStateStream;
  Stream<Duration> get position => _activePlayer.positionStream;
  Stream<Duration?> get duration => _activePlayer.durationStream;

  Future<void> playFile(String path) async {
    try {
      await _activePlayer.setFilePath(path);
      await _activePlayer.play();
    } on PlayerException catch (error) {
      throw AppException('تعذر تشغيل الصوت: ${error.message}');
    }
  }

  Future<void> pause() => _activePlayer.pause();
  Future<void> resume() => _activePlayer.play();
  Future<void> stop() => _activePlayer.stop();
  Future<void> seek(Duration position) => _activePlayer.seek(position);
  Future<void> dispose() async {
    final player = _player;
    if (player != null) await player.dispose();
  }
}
