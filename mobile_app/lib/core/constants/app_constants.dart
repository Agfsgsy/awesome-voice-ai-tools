abstract final class AppConstants {
  static const appName = 'Voice AI Studio';
  static const appVersion = '1.0.0';
  static const mobileApiPrefix = '/api/mobile';
  static const jobPollInterval = Duration(seconds: 2);
  static const requestTimeout = Duration(seconds: 30);
  static const uploadChunkBytes = 5 * 1024 * 1024;
  static const supportedAudioExtensions = <String>{
    'wav',
    'mp3',
    'm4a',
    'aac',
    'flac',
    'ogg',
    'opus',
    'webm',
    'amr',
    '3gp',
  };
  static const supportedDocumentExtensions = <String>{'pdf', 'docx', 'txt'};
}
