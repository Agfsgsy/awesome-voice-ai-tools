import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:dio/dio.dart';
import 'package:path/path.dart' as p;
import 'package:voice_ai_mobile/core/constants/app_constants.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/models/server_session.dart';

typedef UploadProgress = void Function(int sent, int total);

class ApiService {
  ApiService({Dio? dio}) : _dio = dio ?? Dio() {
    _dio.options
      ..connectTimeout = AppConstants.requestTimeout
      ..receiveTimeout = const Duration(minutes: 5)
      ..sendTimeout = const Duration(minutes: 5)
      ..followRedirects = false
      ..headers['Accept'] = 'application/json';
    _dio.interceptors.add(
      InterceptorsWrapper(
        onError: (error, handler) async {
          if (error.response?.statusCode == 401 &&
              error.requestOptions.extra['retried'] != true &&
              error.requestOptions.extra['skipAuthRefresh'] != true &&
              _refresh != null) {
            try {
              final token = await _refresh!();
              if (token != null) {
                final request = error.requestOptions;
                request
                  ..headers['Authorization'] = 'Bearer $token'
                  ..extra['retried'] = true;
                return handler.resolve(await _dio.fetch<dynamic>(request));
              }
            } on Object {
              // يعاد الخطأ الأصلي كي تظهر رسالة الجلسة العربية الموحدة.
            }
          }
          handler.next(error);
        },
      ),
    );
  }

  final Dio _dio;
  String? _baseUrl;
  String? _token;
  Future<String?> Function()? _refresh;

  String get baseUrl => _baseUrl ?? '';

  void configure({required String serverUrl, String? accessToken, Future<String?> Function()? refresh}) {
    _baseUrl = normalizeServerUrl(serverUrl);
    _token = accessToken;
    _refresh = refresh;
    _dio.options.baseUrl = '$_baseUrl${AppConstants.mobileApiPrefix}';
    _setToken(accessToken);
  }

  void updateToken(String token) {
    _token = token;
    _setToken(token);
  }

  void _setToken(String? token) {
    if (token == null || token.isEmpty) {
      _dio.options.headers.remove('Authorization');
    } else {
      _dio.options.headers['Authorization'] = 'Bearer $token';
    }
  }

  static String normalizeServerUrl(String input) {
    final raw = input.trim().replaceAll(RegExp(r'/+$'), '');
    final uri = Uri.tryParse(raw);
    if (uri == null || !uri.hasScheme || !uri.hasAuthority || !{'http', 'https'}.contains(uri.scheme)) {
      throw const AppException('عنوان الخادم غير صالح. مثال: http://voice-ai.local:8000');
    }
    if (uri.scheme == 'http' && !_isPrivateHost(uri.host)) {
      throw const AppException('استخدم HTTPS عند الاتصال بخادم خارج الشبكة المحلية.');
    }
    return uri.replace(path: '', query: null, fragment: null).toString().replaceAll(RegExp(r'/+$'), '');
  }

  static bool _isPrivateHost(String host) {
    if (host == 'localhost' || host.endsWith('.local')) return true;
    final address = InternetAddress.tryParse(host);
    if (address == null) return false;
    if (address.isLoopback || address.type == InternetAddressType.unix) return true;
    final bytes = address.rawAddress;
    if (address.type == InternetAddressType.IPv4) {
      return bytes[0] == 10 ||
          (bytes[0] == 172 && bytes[1] >= 16 && bytes[1] <= 31) ||
          (bytes[0] == 192 && bytes[1] == 168) ||
          (bytes[0] == 169 && bytes[1] == 254);
    }
    return bytes.isNotEmpty && ((bytes[0] & 0xFE) == 0xFC || (bytes[0] == 0xFE && (bytes[1] & 0xC0) == 0x80));
  }

  Future<Map<String, dynamic>> status({String? serverUrl}) async {
    try {
      if (serverUrl != null) configure(serverUrl: serverUrl);
      return _map((await _dio.get<dynamic>('/status')).data);
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<ServerSession> pair({
    required String serverUrl,
    required String pairingId,
    required String pairingCode,
    required String deviceName,
  }) async {
    final normalized = normalizeServerUrl(serverUrl);
    configure(serverUrl: normalized);
    try {
      final paired = _map(
        (await _dio.post<dynamic>(
          '/pair',
          data: <String, dynamic>{
            'pairing_id': pairingId,
            'pairing_code': pairingCode,
            'device_name': deviceName,
            'platform': Platform.operatingSystem,
            'app_version': AppConstants.appVersion,
          },
        ))
            .data,
      );
      final auth = _map(
        (await _dio.post<dynamic>(
          '/auth',
          data: <String, dynamic>{
            'device_id': paired['device_id'],
            'device_token': paired['device_token'],
          },
        ))
            .data,
      );
      final session = ServerSession(
        serverUrl: normalized,
        deviceId: paired['device_id'] as String,
        deviceToken: paired['device_token'] as String,
        accessToken: auth['access_token'] as String,
        expiresAt: DateTime.parse(auth['expires_at'] as String),
      );
      configure(serverUrl: normalized, accessToken: session.accessToken);
      return session;
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<Map<String, dynamic>> authenticate(String deviceId, String deviceToken) async {
    try {
      return _map(
        (await _dio.post<dynamic>(
          '/auth',
          data: <String, dynamic>{'device_id': deviceId, 'device_token': deviceToken},
          options: Options(extra: <String, bool>{'skipAuthRefresh': true}),
        ))
            .data,
      );
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<List<EngineInfo>> engines() async {
    try {
      final data = _map((await _dio.get<dynamic>('/engines')).data);
      return _list(data['engines']).map((value) => EngineInfo.fromJson(_map(value))).toList();
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<List<MobileFileInfo>> files() async {
    try {
      final data = _map((await _dio.get<dynamic>('/files')).data);
      return _list(data['files']).map((value) => MobileFileInfo.fromJson(_map(value))).toList();
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<SelectedReference> analyzeReference(
    String localPath, {
    UploadProgress? onProgress,
    CancelToken? cancelToken,
  }) async {
    try {
      final form = FormData.fromMap(<String, dynamic>{
        'file': await MultipartFile.fromFile(localPath, filename: p.basename(localPath)),
      });
      final data = _map(
        (await _dio.post<dynamic>(
          '/reference/analyze',
          data: form,
          onSendProgress: onProgress,
          cancelToken: cancelToken,
        ))
            .data,
      );
      return SelectedReference(
        localPath: localPath,
        fileId: data['file_id'] as String,
        analysis: AudioAnalysis.fromJson(_map(data['analysis'])),
      );
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<SelectedReference> analyzeReferenceId(String fileId, String localPath) async {
    try {
      final data = _map(
        (await _dio.post<dynamic>(
          '/reference/analyze',
          data: FormData.fromMap(<String, dynamic>{'file_id': fileId}),
        ))
            .data,
      );
      return SelectedReference(
        localPath: localPath,
        fileId: data['file_id'] as String,
        analysis: AudioAnalysis.fromJson(_map(data['analysis'])),
      );
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<String> uploadResumable(
    String path, {
    UploadProgress? onProgress,
    CancelToken? cancelToken,
  }) async {
    final source = File(path);
    if (!await source.exists()) throw const AppException('الملف المحدد غير موجود.');
    final total = await source.length();
    if (total == 0) throw const AppException('الملف المحدد فارغ.');
    final random = Random.secure();
    final uploadId = '${DateTime.now().microsecondsSinceEpoch}_${random.nextInt(1 << 32).toRadixString(16)}';
    var offset = 0;
    final handle = await source.open();
    try {
      while (offset < total) {
        await handle.setPosition(offset);
        final count = min(AppConstants.uploadChunkBytes, total - offset);
        final chunk = await handle.read(count);
        if (chunk.isEmpty) throw const AppException('فشل قراءة الملف أثناء الرفع.');
        var retryDelay = const Duration(seconds: 2);
        while (true) {
          try {
            final form = FormData.fromMap(<String, dynamic>{
              'upload_id': uploadId,
              'filename': p.basename(path),
              'offset': offset,
              'total_size': total,
              'file': MultipartFile.fromBytes(chunk, filename: 'chunk.bin'),
            });
            final data = _map(
              (await _dio.post<dynamic>('/uploads', data: form, cancelToken: cancelToken)).data,
            );
            offset = (data['next_offset'] as num).toInt();
            onProgress?.call(offset, total);
            if (data['completed'] == true) return data['file_id'] as String;
            break;
          } on DioException catch (error) {
            final mapped = AppException.fromDio(error);
            if (!mapped.retryable) rethrow;
            await Future<void>.delayed(retryDelay);
            retryDelay = Duration(seconds: (retryDelay.inSeconds * 2).clamp(2, 30));
            try {
              final status = _map(
                (await _dio.get<dynamic>('/uploads/$uploadId', cancelToken: cancelToken)).data,
              );
              offset = (status['next_offset'] as num).toInt();
              onProgress?.call(offset, total);
              if (status['completed'] == true) return status['file_id'] as String;
              break;
            } on DioException catch (statusError) {
              if (!AppException.fromDio(statusError).retryable) rethrow;
            }
          }
        }
      }
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    } finally {
      await handle.close();
    }
    throw const AppException('فشل رفع الملف.', retryable: true);
  }

  Future<MobileJob> synthesize({
    required String text,
    required String engine,
    required String voice,
    required double speed,
    required int candidateCount,
    Map<String, String> providerHeaders = const <String, String>{},
  }) => _createJob(
        '/voice/synthesize',
        <String, dynamic>{
          'text': text,
          'engine': engine,
          'language': 'ar',
          'voice': voice,
          'speed': speed,
          'candidate_count': candidateCount,
        },
        headers: providerHeaders,
      );

  Future<MobileJob> cloneVoice({
    required String referenceFileId,
    required String text,
    required String engine,
    required int candidateCount,
    required String rights,
    required String consentStatement,
  }) =>
      _createJob('/voice/clone', <String, dynamic>{
        'reference_file_id': referenceFileId,
        'text': text,
        'engine': engine,
        'language': 'ar',
        'candidate_count': candidateCount,
        'consent_confirmed': true,
        'voice_rights': rights,
        'consent_statement': consentStatement,
      });

  Future<MobileJob> prepareEngine(String engine, {String? modelName}) =>
      _createJob('/engines/$engine/prepare', <String, dynamic>{'model_name': modelName});

  Future<MobileJob> readDocument({
    String? path,
    String? text,
    required String engine,
    required String voice,
    required double speed,
    required bool normalizeNumbers,
    Map<String, String> providerHeaders = const <String, String>{},
  }) async {
    try {
      final values = <String, dynamic>{
        'engine': engine,
        'language': 'ar',
        'voice': voice,
        'speed': speed,
        'normalize_numbers': normalizeNumbers,
      };
      if (path != null) {
        values['file'] = await MultipartFile.fromFile(path, filename: p.basename(path));
      } else {
        values['text'] = text;
      }
      final response = await _dio.post<dynamic>(
        '/read/document',
        data: FormData.fromMap(values),
        options: Options(headers: providerHeaders),
      );
      return MobileJob.fromJson(_map(response.data));
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<MobileJob> generateSong({
    required String title,
    required String lyrics,
    required String style,
    required String engine,
    required String voice,
    required int candidateCount,
    required double tempo,
    required double pitch,
    required double reverb,
    String? instrumentalFileId,
    Map<String, String> providerHeaders = const <String, String>{},
  }) =>
      _createJob(
        '/song/generate',
        <String, dynamic>{
          'title': title,
          'lyrics': lyrics,
          'style': style,
          'engine': engine,
          'language': 'ar',
          'voice': voice,
          'candidate_count': candidateCount,
          'tempo': tempo,
          'pitch_semitones': pitch,
          'reverb': reverb,
          'instrumental_file_id': instrumentalFileId,
        },
        headers: providerHeaders,
      );

  Future<MobileJob> _createJob(String endpoint, Map<String, dynamic> payload, {Map<String, String>? headers}) async {
    try {
      final response = await _dio.post<dynamic>(endpoint, data: payload, options: Options(headers: headers));
      return MobileJob.fromJson(_map(response.data));
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<MobileJob> job(String id) async {
    try {
      return MobileJob.fromJson(_map((await _dio.get<dynamic>('/jobs/$id')).data));
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<MobileJob> cancelJob(String id) async {
    try {
      return MobileJob.fromJson(_map((await _dio.post<dynamic>('/jobs/$id/cancel')).data));
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<void> deleteFile(String id) async {
    try {
      await _dio.delete<dynamic>('/files/$id');
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<String> shareFile(String id) async {
    try {
      final data = _map((await _dio.post<dynamic>('/files/$id/share')).data);
      return data['share_url'] as String;
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Future<String> downloadFile(String id, String destination, {UploadProgress? onProgress}) async {
    final partial = '$destination.part';
    final partialFile = File(partial);
    final existing = await partialFile.exists() ? await partialFile.length() : 0;
    try {
      final response = await _dio.download(
        '/files/$id',
        partial,
        options: Options(headers: existing > 0 ? <String, String>{'Range': 'bytes=$existing-'} : null),
        onReceiveProgress: (received, total) => onProgress?.call(existing + received, total > 0 ? existing + total : 0),
        deleteOnError: false,
        fileAccessMode: existing > 0 ? FileAccessMode.append : FileAccessMode.write,
      );
      if (existing > 0 && response.statusCode != HttpStatus.partialContent) {
        await partialFile.delete();
        await _dio.download(
          '/files/$id',
          partial,
          onReceiveProgress: (received, total) => onProgress?.call(received, total),
          deleteOnError: false,
          fileAccessMode: FileAccessMode.write,
        );
      }
      final completed = await partialFile.length();
      if (completed == 0) throw const AppException('الملف الناتج غير صالح.');
      final destinationFile = File(destination);
      if (await destinationFile.exists()) await destinationFile.delete();
      await partialFile.rename(destination);
      return destination;
    } on DioException catch (error) {
      throw AppException.fromDio(error);
    }
  }

  Map<String, String> providerHeaders({String? geminiKey, String? geminiModel, String? elevenLabsKey, String? elevenLabsModel}) {
    if (!baseUrl.startsWith('https://')) return const <String, String>{};
    return <String, String>{
      if (geminiKey?.isNotEmpty ?? false) 'X-Gemini-Api-Key': geminiKey!,
      if (geminiModel?.isNotEmpty ?? false) 'X-Gemini-Model': geminiModel!,
      if (elevenLabsKey?.isNotEmpty ?? false) 'X-ElevenLabs-Api-Key': elevenLabsKey!,
      if (elevenLabsModel?.isNotEmpty ?? false) 'X-ElevenLabs-Model': elevenLabsModel!,
    };
  }

  static Map<String, dynamic> _map(Object? value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map<Object?, Object?>) return value.map((key, item) => MapEntry(key.toString(), item));
    throw const AppException('استجابة الخادم غير صالحة.');
  }

  static List<dynamic> _list(Object? value) {
    if (value is List<dynamic>) return value;
    throw const AppException('استجابة الخادم غير صالحة.');
  }
}
