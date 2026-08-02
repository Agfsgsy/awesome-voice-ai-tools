import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/models/cloud_provider_models.dart';

typedef CloudProgress = void Function(int completed, int total);
typedef OutputDirectoryResolver = Future<Directory> Function();

class CloudProviderService {
  CloudProviderService({
    Dio? dio,
    String geminiBaseUrl = 'https://generativelanguage.googleapis.com',
    String elevenLabsBaseUrl = 'https://api.elevenlabs.io',
    OutputDirectoryResolver? outputDirectory,
  })  : _dio = dio ?? Dio(),
        _geminiBaseUrl = geminiBaseUrl,
        _elevenLabsBaseUrl = elevenLabsBaseUrl,
        _outputDirectory = outputDirectory ?? getApplicationDocumentsDirectory {
    _dio.options
      ..connectTimeout = const Duration(seconds: 30)
      ..sendTimeout = const Duration(minutes: 5)
      ..receiveTimeout = const Duration(minutes: 5)
      ..headers['Accept'] = 'application/json';
  }

  final Dio _dio;
  final String _geminiBaseUrl;
  final String _elevenLabsBaseUrl;
  final OutputDirectoryResolver _outputDirectory;

  static const geminiVoices = <String>[
    'Kore',
    'Sulafat',
    'Achernar',
    'Aoede',
    'Gacrux',
    'Iapetus',
    'Vindemiatrix',
    'Zephyr',
    'Puck',
    'Charon',
  ];

  Future<CloudProviderStatus> checkGemini({
    required String apiKey,
    required String model,
    String textModel = 'gemini-3.6-flash',
    String voice = 'Kore',
    bool verifyGeneration = false,
    CancelToken? cancelToken,
  }) async {
    if (apiKey.trim().isEmpty) {
      return const CloudProviderStatus(
        provider: 'gemini',
        configured: false,
        available: false,
        message: 'أضف مفتاح Gemini من الإعدادات.',
      );
    }
    final selectedModel = _normalizeGeminiModel(
      model,
      fallback: 'gemini-3.1-flash-tts-preview',
    );
    final selectedTextModel = _normalizeGeminiModel(
      textModel,
      fallback: 'gemini-3.6-flash',
    );
    try {
      await Future.wait(<Future<void>>[
        _getGeminiModel(
          apiKey: apiKey,
          model: selectedModel,
          cancelToken: cancelToken,
        ),
        if (selectedTextModel != selectedModel)
          _getGeminiModel(
            apiKey: apiKey,
            model: selectedTextModel,
            cancelToken: cancelToken,
          ),
      ]);
      final capabilities = <String>[
        'مفتاح Gemini صالح لدى Google',
        'نموذج الصوت $selectedModel متاح',
        'نموذج التحليل $selectedTextModel متاح',
      ];
      if (verifyGeneration) {
        final audio = await _requestGeminiAudio(
          apiKey: apiKey,
          model: selectedModel,
          voice: voice,
          prompt: 'اقرأ بوضوح: اختبار اتصال ناجح.',
          cancelToken: cancelToken,
        );
        _decodeGeminiAudio(audio);
        capabilities.add('تم إنشاء عينة صوت حقيقية والتحقق من سلامتها');
      }
      return CloudProviderStatus(
        provider: 'gemini',
        configured: true,
        available: true,
        message: verifyGeneration
            ? 'Gemini متصل فعليًا 100% وتم توليد عينة صوت ناجحة.'
            : 'Gemini متصل والمفتاح والنماذج متاحة.',
        capabilities: capabilities,
        verifiedByGeneration: verifyGeneration,
      );
    } on DioException catch (error) {
      throw _mapProviderError(error, 'Gemini');
    }
  }

  Future<void> _getGeminiModel({
    required String apiKey,
    required String model,
    CancelToken? cancelToken,
  }) async {
    await _dio.get<dynamic>(
      '$_geminiBaseUrl/v1beta/models/${Uri.encodeComponent(model)}',
      options: Options(
        headers: <String, String>{'x-goog-api-key': apiKey.trim()},
      ),
      cancelToken: cancelToken,
    );
  }

  Future<_GeminiAudio> _requestGeminiAudio({
    required String apiKey,
    required String model,
    required String voice,
    required String prompt,
    CancelToken? cancelToken,
  }) async {
    final selectedVoice = geminiVoices.contains(voice) ? voice : 'Kore';
    final response = await _dio.post<dynamic>(
      '$_geminiBaseUrl/v1beta/models/${Uri.encodeComponent(model)}:generateContent',
      data: <String, dynamic>{
        'contents': <Map<String, dynamic>>[
          <String, dynamic>{
            'parts': <Map<String, String>>[
              <String, String>{'text': prompt},
            ],
          },
        ],
        'generationConfig': <String, dynamic>{
          'responseModalities': <String>['AUDIO'],
          'speechConfig': <String, dynamic>{
            'voiceConfig': <String, dynamic>{
              'prebuiltVoiceConfig': <String, String>{
                'voiceName': selectedVoice,
              },
            },
          },
        },
      },
      options: Options(
        headers: <String, String>{
          'x-goog-api-key': apiKey.trim(),
          Headers.contentTypeHeader: Headers.jsonContentType,
        },
      ),
      cancelToken: cancelToken,
    );
    return _extractGeminiAudio(_asMap(response.data));
  }

  Future<String> transcribeGemini({
    required String apiKey,
    required String model,
    required String audioPath,
    bool includeTimestamps = true,
    CancelToken? cancelToken,
    ProgressCallback? onProgress,
  }) async {
    if (apiKey.trim().isEmpty) {
      throw const AppException('أضف مفتاح Gemini من الإعدادات أولًا.');
    }
    final source = File(audioPath);
    if (!await source.exists() || await source.length() <= 44) {
      throw const AppException('الملف الصوتي المحدد غير صالح.');
    }
    final size = await source.length();
    final mimeType = _audioMimeType(audioPath);
    String? uploadedName;
    try {
      final Map<String, dynamic> audioInput;
      if (size <= 14 * 1024 * 1024) {
        final bytes = await source.readAsBytes();
        onProgress?.call(bytes.length, bytes.length);
        audioInput = <String, dynamic>{
          'type': 'audio',
          'data': base64Encode(bytes),
          'mime_type': mimeType,
        };
      } else {
        final uploaded = await _uploadGeminiFile(
          apiKey: apiKey,
          source: source,
          mimeType: mimeType,
          cancelToken: cancelToken,
          onProgress: onProgress,
        );
        uploadedName = uploaded.name;
        audioInput = <String, dynamic>{
          'type': 'audio',
          'uri': uploaded.uri,
          'mime_type': uploaded.mimeType,
        };
      }
      final prompt = includeTimestamps
          ? 'حوّل الكلام في هذا التسجيل إلى نص عربي دقيق. اذكر الطوابع الزمنية بصيغة MM:SS عند تغيّر المتحدث، ولا تضف شرحًا أو كلامًا غير مسموع.'
          : 'حوّل الكلام في هذا التسجيل إلى نص عربي دقيق فقط، دون شرح أو إضافة.';
      final response = await _dio.post<dynamic>(
        '$_geminiBaseUrl/v1beta/interactions',
        data: <String, dynamic>{
          'model': _normalizeGeminiModel(
            model,
            fallback: 'gemini-3.6-flash',
          ),
          'input': <Map<String, dynamic>>[
            <String, dynamic>{'type': 'text', 'text': prompt},
            audioInput,
          ],
          'generation_config': const <String, dynamic>{
            'thinking_level': 'minimal',
          },
          'store': false,
        },
        options: Options(
          headers: <String, String>{
            'x-goog-api-key': apiKey,
            'Api-Revision': '2026-05-20',
            Headers.contentTypeHeader: Headers.jsonContentType,
          },
        ),
        cancelToken: cancelToken,
      );
      final transcript = _extractGeminiText(_asMap(response.data)).trim();
      if (transcript.isEmpty) {
        throw const AppException('لم يتمكن Gemini من استخراج كلام واضح.');
      }
      return transcript;
    } on DioException catch (error) {
      throw _mapProviderError(error, 'Gemini');
    } finally {
      if (uploadedName != null) {
        try {
          await _dio.delete<dynamic>(
            '$_geminiBaseUrl/v1beta/$uploadedName',
            options: Options(
              headers: <String, String>{'x-goog-api-key': apiKey},
            ),
          );
        } on Object {
          // تنتهي ملفات Gemini المؤقتة تلقائيًا، والحذف الفوري أفضل جهدًا.
        }
      }
    }
  }

  Future<CloudProviderStatus> checkElevenLabs({
    required String apiKey,
    String ttsModel = 'eleven_multilingual_v2',
    String stsModel = 'eleven_multilingual_sts_v2',
    bool verifyGeneration = false,
    CancelToken? cancelToken,
  }) async {
    if (apiKey.trim().isEmpty) {
      return const CloudProviderStatus(
        provider: 'elevenlabs',
        configured: false,
        available: false,
        message: 'أضف مفتاح ElevenLabs من الإعدادات.',
      );
    }
    try {
      final data = _asMap(
        (await _dio.get<dynamic>(
          '$_elevenLabsBaseUrl/v1/user/subscription',
          options: Options(headers: <String, String>{'xi-api-key': apiKey}),
          cancelToken: cancelToken,
        ))
            .data,
      );
      final modelsResponse = await _dio.get<dynamic>(
        '$_elevenLabsBaseUrl/v1/models',
        options: Options(headers: <String, String>{'xi-api-key': apiKey}),
        cancelToken: cancelToken,
      );
      final models = _asMapList(modelsResponse.data);
      final selectedTtsModel = _findElevenLabsModel(models, ttsModel);
      if (selectedTtsModel['can_do_text_to_speech'] == false) {
        throw AppException(
          'نموذج ElevenLabs $ttsModel لا يدعم توليد الصوت.',
        );
      }
      final selectedStsModel = _findElevenLabsModel(models, stsModel);
      if (selectedStsModel['can_do_voice_conversion'] == false) {
        throw AppException(
          'نموذج ElevenLabs $stsModel لا يدعم تغيير الصوت.',
        );
      }
      final used = (data['character_count'] as num?)?.toInt();
      final limit = (data['character_limit'] as num?)?.toInt();
      final remaining = used == null || limit == null ? null : limit - used;
      final capabilities = <String>[
        'مفتاح ElevenLabs صالح والحساب قابل للوصول',
        'نموذج التوليد $ttsModel متاح',
        'نموذج مغير الصوت $stsModel متاح',
      ];
      if (verifyGeneration) {
        final voices = await listElevenLabsVoices(
          apiKey: apiKey,
          cancelToken: cancelToken,
        );
        final bytes = await _requestElevenLabsAudio(
          apiKey: apiKey,
          model: ttsModel,
          voiceId: voices.first.id,
          text: 'اختبار',
          cancelToken: cancelToken,
        );
        if (bytes.length < 128) {
          throw const AppException(
            'اتصل المفتاح لكن ElevenLabs أعادت عينة صوت غير صالحة.',
          );
        }
        capabilities.add('تم إنشاء عينة صوت حقيقية والتحقق من سلامتها');
      }
      return CloudProviderStatus(
        provider: 'elevenlabs',
        configured: true,
        available: data['status'] != 'past_due',
        message: data['status'] == 'past_due'
            ? 'حساب ElevenLabs يحتاج مراجعة الفوترة.'
            : verifyGeneration
                ? 'ElevenLabs متصل فعليًا 100% وتم توليد عينة صوت ناجحة.'
                : 'ElevenLabs متصل والمفتاح والنماذج متاحة.',
        plan: data['tier']?.toString(),
        remainingCharacters: remaining?.clamp(0, 1 << 31).toInt(),
        canCloneVoice: data['can_use_instant_voice_cloning'] as bool?,
        capabilities: capabilities,
        verifiedByGeneration: verifyGeneration,
      );
    } on DioException catch (error) {
      throw _mapProviderError(error, 'ElevenLabs');
    }
  }

  Map<String, dynamic> _findElevenLabsModel(
    List<Map<String, dynamic>> models,
    String requestedModel,
  ) {
    final normalized = requestedModel.trim();
    for (final model in models) {
      if (model['model_id'] == normalized) return model;
    }
    throw AppException(
      'نموذج ElevenLabs $normalized غير متاح لهذا المفتاح أو الحساب.',
    );
  }

  Future<List<int>> _requestElevenLabsAudio({
    required String apiKey,
    required String model,
    required String voiceId,
    required String text,
    int? seed,
    CancelToken? cancelToken,
  }) async {
    final response = await _dio.post<List<int>>(
      '$_elevenLabsBaseUrl/v1/text-to-speech/${Uri.encodeComponent(voiceId)}',
      queryParameters: const <String, dynamic>{
        'output_format': 'mp3_44100_128',
      },
      data: <String, dynamic>{
        'text': text,
        'model_id': model,
        'apply_text_normalization': 'on',
        if (seed != null) 'seed': seed & 0xffffffff,
      },
      options: Options(
        responseType: ResponseType.bytes,
        headers: <String, String>{
          'xi-api-key': apiKey.trim(),
          Headers.contentTypeHeader: Headers.jsonContentType,
          'Accept': 'audio/mpeg',
        },
      ),
      cancelToken: cancelToken,
    );
    return response.data ?? const <int>[];
  }

  Future<List<CloudVoice>> listElevenLabsVoices({
    required String apiKey,
    CancelToken? cancelToken,
  }) async {
    if (apiKey.trim().isEmpty) {
      throw const AppException('أضف مفتاح ElevenLabs من الإعدادات أولًا.');
    }
    try {
      final data = _asMap(
        (await _dio.get<dynamic>(
          '$_elevenLabsBaseUrl/v2/voices',
          queryParameters: const <String, dynamic>{
            'page_size': 100,
            'include_total_count': false,
            'sort': 'name',
            'sort_direction': 'asc',
          },
          options: Options(headers: <String, String>{'xi-api-key': apiKey}),
          cancelToken: cancelToken,
        ))
            .data,
      );
      final voices = (data['voices'] as List<dynamic>? ?? const <dynamic>[])
          .whereType<Map<String, dynamic>>()
          .map(CloudVoice.fromElevenLabs)
          .where((voice) => voice.id.isNotEmpty)
          .toList();
      if (voices.isEmpty) {
        throw const AppException('لا توجد أصوات متاحة في حساب ElevenLabs.');
      }
      return voices;
    } on DioException catch (error) {
      throw _mapProviderError(error, 'ElevenLabs');
    }
  }

  Future<CloudVoice> cloneElevenLabsVoice({
    required String apiKey,
    required String referencePath,
    required String voiceName,
    required String rights,
    bool removeBackgroundNoise = false,
    CancelToken? cancelToken,
    ProgressCallback? onSendProgress,
  }) async {
    final source = File(referencePath);
    if (!await source.exists() || await source.length() <= 44) {
      throw const AppException('التسجيل المرجعي غير صالح أو لم يعد موجودًا.');
    }
    if (apiKey.trim().isEmpty) {
      throw const AppException('أضف مفتاح ElevenLabs من الإعدادات أولًا.');
    }
    final safeName = voiceName.trim();
    if (safeName.length < 2) {
      throw const AppException('اكتب اسمًا واضحًا للصوت المستنسخ.');
    }
    final form = FormData();
    form.fields
      ..add(MapEntry<String, String>('name', safeName))
      ..add(
        MapEntry<String, String>(
          'description',
          rights == 'self'
              ? 'Authorized self-owned voice from Voice AI Studio mobile'
              : 'Explicitly authorized voice from Voice AI Studio mobile',
        ),
      )
      ..add(
        MapEntry<String, String>(
          'remove_background_noise',
          removeBackgroundNoise.toString(),
        ),
      );
    form.files.add(
      MapEntry<String, MultipartFile>(
        'files',
        await MultipartFile.fromFile(
          referencePath,
          filename: p.basename(referencePath),
        ),
      ),
    );
    try {
      final data = _asMap(
        (await _dio.post<dynamic>(
          '$_elevenLabsBaseUrl/v1/voices/add',
          data: form,
          options: Options(headers: <String, String>{'xi-api-key': apiKey}),
          cancelToken: cancelToken,
          onSendProgress: onSendProgress,
        ))
            .data,
      );
      final voiceId = data['voice_id'] as String?;
      if (voiceId == null || voiceId.isEmpty) {
        throw const AppException('لم تُرجع ElevenLabs معرّفًا للصوت المستنسخ.');
      }
      return CloudVoice(
        id: voiceId,
        name: safeName,
        category: 'cloned',
        description: data['requires_verification'] == true
            ? 'يتطلب التحقق من الصوت داخل حساب ElevenLabs.'
            : 'صوت مستنسخ وجاهز.',
      );
    } on DioException catch (error) {
      throw _mapProviderError(error, 'ElevenLabs');
    }
  }

  Future<Map<String, dynamic>> synthesizeCandidates({
    required String provider,
    required String apiKey,
    required String model,
    required String voice,
    required String text,
    int candidateCount = 1,
    String? style,
    CancelToken? cancelToken,
    CloudProgress? onProgress,
  }) async {
    final cleanText = text.trim();
    if (cleanText.isEmpty) {
      throw const AppException('أدخل نصًا واضحًا لتحويله إلى صوت.');
    }
    final total = candidateCount.clamp(1, 5);
    final candidates = <Map<String, dynamic>>[];
    for (var index = 0; index < total; index++) {
      if (cancelToken?.isCancelled == true) {
        throw const AppException('المهمة أُلغيت.', code: 'cancelled');
      }
      final path = provider == 'gemini_direct'
          ? await synthesizeGemini(
              apiKey: apiKey,
              model: model,
              voice: voice,
              text: cleanText,
              style: style,
              candidateIndex: index,
              cancelToken: cancelToken,
            )
          : await synthesizeElevenLabs(
              apiKey: apiKey,
              model: model,
              voiceId: voice,
              text: cleanText,
              seed: DateTime.now().microsecondsSinceEpoch + index,
              cancelToken: cancelToken,
            );
      candidates.add(<String, dynamic>{
        'candidate_id': 'cloud_${index + 1}',
        'local_path': path,
        'name': p.basename(path),
        'provider': provider,
      });
      onProgress?.call(index + 1, total);
    }
    return <String, dynamic>{
      'candidates': candidates,
      'best_candidate_id': candidates.first['candidate_id'],
      'provider': provider,
    };
  }

  Future<String> synthesizeGemini({
    required String apiKey,
    required String model,
    required String voice,
    required String text,
    String? style,
    int candidateIndex = 0,
    CancelToken? cancelToken,
  }) async {
    if (apiKey.trim().isEmpty) {
      throw const AppException('أضف مفتاح Gemini من الإعدادات أولًا.');
    }
    final selectedVoice = geminiVoices.contains(voice) ? voice : 'Kore';
    final prompt = <String>[
      if (style?.trim().isNotEmpty == true) style!.trim(),
      'اقرأ النص العربي التالي كاملًا دون إضافة أو حذف:',
      text,
      if (candidateIndex > 0)
        'قدّم أداءً طبيعيًا بديلًا رقم ${candidateIndex + 1}.',
    ].join('\n');
    try {
      final audio = await _requestGeminiAudio(
        apiKey: apiKey,
        model: _normalizeGeminiModel(
          model,
          fallback: 'gemini-3.1-flash-tts-preview',
        ),
        voice: selectedVoice,
        prompt: prompt,
        cancelToken: cancelToken,
      );
      final normalized = _decodeGeminiAudio(audio);
      return _saveOutput(normalized, 'gemini', 'wav');
    } on FormatException {
      throw const AppException('أعاد Gemini ملفًا صوتيًا غير صالح.');
    } on DioException catch (error) {
      throw _mapProviderError(error, 'Gemini');
    }
  }

  Future<String> synthesizeElevenLabs({
    required String apiKey,
    required String model,
    required String voiceId,
    required String text,
    int? seed,
    CancelToken? cancelToken,
  }) async {
    if (apiKey.trim().isEmpty) {
      throw const AppException('أضف مفتاح ElevenLabs من الإعدادات أولًا.');
    }
    if (voiceId.trim().isEmpty || voiceId == 'default') {
      throw const AppException('اختر صوتًا من أصوات ElevenLabs أولًا.');
    }
    try {
      final bytes = await _requestElevenLabsAudio(
        apiKey: apiKey,
        model: model,
        voiceId: voiceId,
        text: text,
        seed: seed,
        cancelToken: cancelToken,
      );
      if (bytes.length < 128) {
        throw const AppException('أعادت ElevenLabs ملفًا صوتيًا غير صالح.');
      }
      return _saveOutput(bytes, 'elevenlabs', 'mp3');
    } on DioException catch (error) {
      throw _mapProviderError(error, 'ElevenLabs');
    }
  }

  Future<String> changeVoiceElevenLabs({
    required String apiKey,
    required String model,
    required String voiceId,
    required String sourcePath,
    bool removeBackgroundNoise = false,
    CancelToken? cancelToken,
    ProgressCallback? onSendProgress,
  }) async {
    final source = File(sourcePath);
    if (!await source.exists()) {
      throw const AppException('الملف الصوتي المحدد غير موجود.');
    }
    final form = FormData();
    form.fields
      ..add(MapEntry<String, String>('model_id', model))
      ..add(
        MapEntry<String, String>(
          'remove_background_noise',
          removeBackgroundNoise.toString(),
        ),
      );
    form.files.add(
      MapEntry<String, MultipartFile>(
        'audio',
        await MultipartFile.fromFile(
          sourcePath,
          filename: p.basename(sourcePath),
        ),
      ),
    );
    try {
      final response = await _dio.post<List<int>>(
        '$_elevenLabsBaseUrl/v1/speech-to-speech/${Uri.encodeComponent(voiceId)}',
        queryParameters: const <String, dynamic>{
          'output_format': 'mp3_44100_128',
        },
        data: form,
        options: Options(
          responseType: ResponseType.bytes,
          headers: <String, String>{'xi-api-key': apiKey},
        ),
        cancelToken: cancelToken,
        onSendProgress: onSendProgress,
      );
      final bytes = response.data;
      if (bytes == null || bytes.length < 128) {
        throw const AppException('الملف الناتج من مغير الصوت غير صالح.');
      }
      return _saveOutput(bytes, 'voice_change', 'mp3');
    } on DioException catch (error) {
      throw _mapProviderError(error, 'ElevenLabs');
    }
  }

  Future<String> _saveOutput(
    List<int> bytes,
    String prefix,
    String extension,
  ) async {
    final root = await _outputDirectory();
    final directory = Directory(p.join(root.path, 'voice_ai_outputs'));
    await directory.create(recursive: true);
    final file = File(
      p.join(
        directory.path,
        '${prefix}_${DateTime.now().microsecondsSinceEpoch}.$extension',
      ),
    );
    await file.writeAsBytes(bytes, flush: true);
    if (!await file.exists() || await file.length() <= 44) {
      throw const AppException('الملف الناتج غير صالح.');
    }
    return file.path;
  }

  Uint8List _decodeGeminiAudio(_GeminiAudio audio) {
    final List<int> bytes;
    try {
      bytes = base64Decode(audio.data);
    } on FormatException {
      throw const AppException('أعاد Gemini بيانات صوتية تالفة.');
    }
    if (bytes.length < 128) {
      throw const AppException('أعاد Gemini عينة صوت فارغة أو غير صالحة.');
    }
    if (_isWave(bytes)) return Uint8List.fromList(bytes);
    final mimeType = audio.mimeType.toLowerCase();
    if (!mimeType.contains('l16') && !mimeType.contains('pcm')) {
      throw AppException(
        'أعاد Gemini صيغة صوت غير مدعومة: ${audio.mimeType}.',
      );
    }
    return _wrapPcmAsWave(
      bytes,
      sampleRate: audio.sampleRate ??
          _sampleRateFromMime(audio.mimeType) ??
          24000,
    );
  }

  _GeminiAudio _extractGeminiAudio(Map<String, dynamic> response) {
    final candidates = response['candidates'] as List<dynamic>?;
    if (candidates != null) {
      for (final candidate in candidates) {
        if (candidate is! Map<String, dynamic>) continue;
        final content = candidate['content'];
        if (content is! Map<String, dynamic>) continue;
        final parts = content['parts'] as List<dynamic>? ?? const <dynamic>[];
        for (final part in parts) {
          if (part is! Map<String, dynamic>) continue;
          final inline = part['inlineData'] ?? part['inline_data'];
          if (inline is! Map<String, dynamic>) continue;
          final data = inline['data'] as String?;
          if (data == null || data.isEmpty) continue;
          final mimeType = inline['mimeType'] as String? ??
              inline['mime_type'] as String? ??
              'audio/L16;codec=pcm;rate=24000';
          return _GeminiAudio(
            data: data,
            mimeType: mimeType,
            sampleRate: (inline['sampleRate'] as num?)?.toInt() ??
                (inline['sample_rate'] as num?)?.toInt() ??
                _sampleRateFromMime(mimeType),
          );
        }
      }
    }
    final steps = response['steps'] as List<dynamic>? ?? const <dynamic>[];
    for (final step in steps.reversed) {
      if (step is! Map<String, dynamic>) continue;
      final content = step['content'] as List<dynamic>? ?? const <dynamic>[];
      for (final item in content.reversed) {
        if (item is Map<String, dynamic> && item['type'] == 'audio') {
          final data = item['data'] as String?;
          if (data != null && data.isNotEmpty) {
            final mimeType = item['mime_type'] as String? ??
                item['mimeType'] as String? ??
                'audio/L16;codec=pcm;rate=24000';
            return _GeminiAudio(
              data: data,
              mimeType: mimeType,
              sampleRate: (item['sample_rate'] as num?)?.toInt() ??
                  (item['sampleRate'] as num?)?.toInt() ??
                  _sampleRateFromMime(mimeType),
            );
          }
        }
      }
    }
    final legacy = response['output_audio'] ?? response['outputAudio'];
    if (legacy is Map<String, dynamic> && legacy['data'] is String) {
      final mimeType = legacy['mime_type'] as String? ??
          legacy['mimeType'] as String? ??
          'audio/L16;codec=pcm;rate=24000';
      return _GeminiAudio(
        data: legacy['data'] as String,
        mimeType: mimeType,
        sampleRate: (legacy['sample_rate'] as num?)?.toInt() ??
            (legacy['sampleRate'] as num?)?.toInt() ??
            _sampleRateFromMime(mimeType),
      );
    }
    throw const AppException('لم يُرجع Gemini بيانات صوتية.');
  }

  String _extractGeminiText(Map<String, dynamic> response) {
    final direct = response['output_text'];
    if (direct is String && direct.trim().isNotEmpty) return direct;
    final steps = response['steps'] as List<dynamic>? ?? const <dynamic>[];
    for (final step in steps.reversed) {
      if (step is! Map<String, dynamic>) continue;
      final content = step['content'] as List<dynamic>? ?? const <dynamic>[];
      for (final item in content.reversed) {
        if (item is Map<String, dynamic> && item['type'] == 'text') {
          final value = item['text'];
          if (value is String && value.trim().isNotEmpty) return value;
        }
      }
    }
    final candidates = response['candidates'] as List<dynamic>?;
    if (candidates != null) {
      for (final candidate in candidates) {
        if (candidate is! Map<String, dynamic>) continue;
        final content = candidate['content'];
        if (content is! Map<String, dynamic>) continue;
        final parts = content['parts'] as List<dynamic>? ?? const <dynamic>[];
        for (final part in parts) {
          if (part is Map<String, dynamic> && part['text'] is String) {
            return part['text'] as String;
          }
        }
      }
    }
    throw const AppException('لم يُرجع Gemini نصًا صالحًا.');
  }

  Future<_GeminiFile> _uploadGeminiFile({
    required String apiKey,
    required File source,
    required String mimeType,
    CancelToken? cancelToken,
    ProgressCallback? onProgress,
  }) async {
    final size = await source.length();
    final start = await _dio.post<dynamic>(
      '$_geminiBaseUrl/upload/v1beta/files',
      data: <String, dynamic>{
        'file': <String, String>{'display_name': p.basename(source.path)},
      },
      options: Options(
        headers: <String, String>{
          'x-goog-api-key': apiKey,
          'X-Goog-Upload-Protocol': 'resumable',
          'X-Goog-Upload-Command': 'start',
          'X-Goog-Upload-Header-Content-Length': '$size',
          'X-Goog-Upload-Header-Content-Type': mimeType,
          Headers.contentTypeHeader: Headers.jsonContentType,
        },
      ),
      cancelToken: cancelToken,
    );
    final uploadUrl = start.headers.value('x-goog-upload-url');
    if (uploadUrl == null || !_isSecureOrLoopbackUrl(uploadUrl)) {
      throw const AppException('تعذر بدء رفع التسجيل إلى Gemini.');
    }
    final uploadedResponse = await _dio.post<dynamic>(
      uploadUrl,
      data: source.openRead(),
      options: Options(
        headers: <String, String>{
          'X-Goog-Upload-Offset': '0',
          'X-Goog-Upload-Command': 'upload, finalize',
          Headers.contentLengthHeader: '$size',
          Headers.contentTypeHeader: mimeType,
        },
      ),
      cancelToken: cancelToken,
      onSendProgress: onProgress,
    );
    var fileData = _asMap(uploadedResponse.data);
    if (fileData['file'] is Map<String, dynamic>) {
      fileData = fileData['file'] as Map<String, dynamic>;
    }
    final name = fileData['name'] as String?;
    var uri = fileData['uri'] as String?;
    var state = fileData['state'] as String? ?? 'ACTIVE';
    if (name == null || name.isEmpty) {
      throw const AppException('لم يُرجع Gemini معرّفًا للملف المرفوع.');
    }
    for (var attempt = 0; state == 'PROCESSING' && attempt < 30; attempt++) {
      await Future<void>.delayed(const Duration(seconds: 2));
      final polled = _asMap(
        (await _dio.get<dynamic>(
          '$_geminiBaseUrl/v1beta/$name',
          options: Options(headers: <String, String>{'x-goog-api-key': apiKey}),
          cancelToken: cancelToken,
        ))
            .data,
      );
      state = polled['state'] as String? ?? state;
      uri = polled['uri'] as String? ?? uri;
      fileData = polled;
    }
    if (state == 'FAILED') {
      throw const AppException('فشل Gemini في معالجة صيغة التسجيل.');
    }
    if (state != 'ACTIVE' || uri == null || uri.isEmpty) {
      throw const AppException(
        'استغرقت معالجة التسجيل وقتًا طويلًا؛ حاول مجددًا.',
      );
    }
    return _GeminiFile(
      name: name,
      uri: uri,
      mimeType: fileData['mimeType'] as String? ??
          fileData['mime_type'] as String? ??
          mimeType,
    );
  }

  String _audioMimeType(String path) {
    return switch (p.extension(path).toLowerCase()) {
      '.wav' => 'audio/wav',
      '.mp3' => 'audio/mp3',
      '.m4a' => 'audio/mp4',
      '.aac' => 'audio/aac',
      '.flac' => 'audio/flac',
      '.ogg' => 'audio/ogg',
      '.opus' => 'audio/ogg',
      '.webm' => 'audio/webm',
      '.amr' => 'audio/amr',
      '.3gp' => 'audio/3gpp',
      _ => 'application/octet-stream',
    };
  }

  bool _isSecureOrLoopbackUrl(String value) {
    final uri = Uri.tryParse(value);
    if (uri == null || !uri.hasAuthority) return false;
    if (uri.scheme == 'https') return true;
    return uri.scheme == 'http' &&
        (uri.host == '127.0.0.1' ||
            uri.host == '::1' ||
            uri.host == 'localhost');
  }

  String _normalizeGeminiModel(String value, {required String fallback}) {
    final cleaned = value.trim().replaceFirst(RegExp(r'^models/'), '');
    return cleaned.isEmpty ? fallback : cleaned;
  }

  bool _isWave(List<int> bytes) =>
      bytes.length > 44 && ascii.decode(bytes.take(4).toList()) == 'RIFF';

  int? _sampleRateFromMime(String mimeType) {
    for (final part in mimeType.split(';')) {
      final pair = part.trim().split('=');
      if (pair.length != 2) continue;
      final key = pair.first.toLowerCase();
      if (key == 'rate' || key == 'samplerate' || key == 'sample_rate') {
        return int.tryParse(pair.last.trim());
      }
    }
    return null;
  }

  Uint8List _wrapPcmAsWave(List<int> pcm, {required int sampleRate}) {
    final output = BytesBuilder(copy: false);
    void text(String value) => output.add(ascii.encode(value));
    void int16(int value) {
      output.add(<int>[value & 0xff, (value >> 8) & 0xff]);
    }

    void int32(int value) {
      output.add(<int>[
        value & 0xff,
        (value >> 8) & 0xff,
        (value >> 16) & 0xff,
        (value >> 24) & 0xff,
      ]);
    }

    text('RIFF');
    int32(36 + pcm.length);
    text('WAVEfmt ');
    int32(16);
    int16(1);
    int16(1);
    int32(sampleRate);
    int32(sampleRate * 2);
    int16(2);
    int16(16);
    text('data');
    int32(pcm.length);
    output.add(pcm);
    return output.takeBytes();
  }

  AppException _mapProviderError(DioException error, String provider) {
    if (error.type == DioExceptionType.cancel) {
      return const AppException('المهمة أُلغيت.', code: 'cancelled');
    }
    final status = error.response?.statusCode;
    final detail = _providerDetail(error.response?.data);
    if (status == 401 || status == 403) {
      return AppException(
        'مفتاح $provider غير صالح أو لا يملك صلاحية هذه الأداة.',
        code: '${provider.toLowerCase()}_auth',
      );
    }
    if (status == 402) {
      return AppException(
        'رصيد أو اشتراك $provider غير كافٍ لإكمال العملية.',
        code: '${provider.toLowerCase()}_billing',
      );
    }
    if (status == 413) {
      return const AppException('الملف كبير جدًا للرفع إلى الخدمة.');
    }
    if (status == 400) {
      if (detail?.toLowerCase().contains('mime_type') == true ||
          detail?.toLowerCase().contains('response_format') == true) {
        return AppException(
          'صيغة طلب الصوت غير متوافقة مع واجهة $provider الحالية. حدّث التطبيق ثم أعد المحاولة.',
          code: '${provider.toLowerCase()}_request_format',
        );
      }
      return AppException(
        'رفضت خدمة $provider إعدادات الطلب أو اسم النموذج. راجع النموذج ثم أعد الفحص.',
        code: '${provider.toLowerCase()}_bad_request',
      );
    }
    if (status == 404) {
      return AppException(
        'النموذج المطلوب غير موجود أو غير متاح لمفتاح $provider.',
        code: '${provider.toLowerCase()}_model_not_found',
      );
    }
    if (status == 422) {
      return AppException(detail ?? 'رفضت الخدمة الملف أو الإعدادات المرسلة.');
    }
    if (status == 429) {
      return AppException(
        'تم بلوغ حد الاستخدام في $provider؛ انتظر قليلًا أو راجع الرصيد.',
        retryable: true,
      );
    }
    if (status != null && status >= 500) {
      return AppException(
        'خدمة $provider غير متاحة مؤقتًا. حاول مرة أخرى.',
        retryable: true,
      );
    }
    final mapped = AppException.fromDio(error);
    if (mapped.code == 'offline') {
      return const AppException(
        'انقطع الإنترنت. أعد المحاولة عند عودة الاتصال.',
        code: 'offline',
        retryable: true,
      );
    }
    return AppException(detail ?? mapped.message, retryable: mapped.retryable);
  }

  String? _providerDetail(Object? data) {
    if (data is Map<String, dynamic>) {
      final detail = data['detail'] ?? data['message'];
      if (detail is String && detail.trim().isNotEmpty) return detail;
      final error = data['error'];
      if (error is Map<String, dynamic>) {
        final message = error['message'];
        if (message is String && message.trim().isNotEmpty) return message;
      }
    }
    return null;
  }

  Map<String, dynamic> _asMap(Object? value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map<Object?, Object?>) {
      return value.map((key, item) => MapEntry(key.toString(), item));
    }
    throw const AppException('استجابة الخدمة السحابية غير صالحة.');
  }

  List<Map<String, dynamic>> _asMapList(Object? value) {
    if (value is! List<dynamic>) {
      throw const AppException('قائمة نماذج الخدمة السحابية غير صالحة.');
    }
    return value
        .whereType<Map<dynamic, dynamic>>()
        .map(
          (item) => item.map(
            (key, entry) => MapEntry(key.toString(), entry),
          ),
        )
        .toList();
  }
}

class _GeminiAudio {
  const _GeminiAudio({
    required this.data,
    required this.mimeType,
    this.sampleRate,
  });

  final String data;
  final String mimeType;
  final int? sampleRate;
}

class _GeminiFile {
  const _GeminiFile({
    required this.name,
    required this.uri,
    required this.mimeType,
  });

  final String name;
  final String uri;
  final String mimeType;
}
