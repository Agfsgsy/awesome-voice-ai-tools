import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:path/path.dart' as p;
import 'package:voice_ai_mobile/core/constants/app_constants.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/core/utils/formatters.dart';
import 'package:voice_ai_mobile/models/cloud_provider_models.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/widgets/audio_analysis_card.dart';
import 'package:voice_ai_mobile/widgets/audio_result_list.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';

class RecorderScreen extends ConsumerStatefulWidget {
  const RecorderScreen({super.key});

  @override
  ConsumerState<RecorderScreen> createState() => _RecorderScreenState();
}

class _RecorderScreenState extends ConsumerState<RecorderScreen> {
  String? _path;
  bool _ownedFile = false;
  bool _recording = false;
  bool _paused = false;
  bool _busy = false;
  int _elapsedSeconds = 0;
  double? _uploadProgress;
  AudioAnalysis? _localAnalysis;
  SelectedReference? _serverReference;
  Timer? _timer;
  CancelToken? _uploadCancelToken;
  CancelToken? _cloudCancelToken;
  double? _cloudProgress;
  String? _transcript;
  Map<String, dynamic>? _processedResult;
  String _effectPreset = 'studio';
  String _selectedElevenVoice = '';
  bool _removeVoiceNoise = false;
  List<CloudVoice> _cloudVoices = const <CloudVoice>[];
  final _trimStartController = TextEditingController(text: '0');
  final _trimEndController = TextEditingController(text: '0');
  CloudProviderConfig _cloudConfig = const CloudProviderConfig(
    geminiApiKey: '',
    geminiModel: 'gemini-3.1-flash-tts-preview',
    geminiVoice: 'Kore',
    elevenLabsApiKey: '',
    elevenLabsModel: 'eleven_multilingual_v2',
  );

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_loadCloudConfig);
  }

  @override
  void dispose() {
    _timer?.cancel();
    _uploadCancelToken?.cancel('ألغى المستخدم عملية الرفع');
    _cloudCancelToken?.cancel();
    _trimStartController.dispose();
    _trimEndController.dispose();
    super.dispose();
  }

  Future<void> _loadCloudConfig() async {
    try {
      final config = await ref.read(cloudProviderConfigProvider.future);
      var voices = const <CloudVoice>[];
      if (config.hasElevenLabs) {
        try {
          voices = await ref
              .read(cloudProviderServiceProvider)
              .listElevenLabsVoices(apiKey: config.elevenLabsApiKey);
        } on Object {
          voices = const <CloudVoice>[];
        }
      }
      if (mounted) {
        setState(() {
          _cloudConfig = config;
          _cloudVoices = voices;
          if (voices.isNotEmpty) _selectedElevenVoice = voices.first.id;
        });
      }
    } on Object {
      // تعرض أداة التفريغ رسالة الإعداد عند تشغيلها.
    }
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && _recording && !_paused) setState(() => _elapsedSeconds++);
    });
  }

  Future<void> _start() async {
    try {
      final path = await ref.read(recorderServiceProvider).start();
      setState(() {
        _path = path;
        _ownedFile = true;
        _recording = true;
        _paused = false;
        _elapsedSeconds = 0;
        _localAnalysis = null;
        _serverReference = null;
        _transcript = null;
        _processedResult = null;
      });
      _startTimer();
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    }
  }

  Future<void> _pauseOrResume() async {
    try {
      if (_paused) {
        await ref.read(recorderServiceProvider).resume();
      } else {
        await ref.read(recorderServiceProvider).pause();
      }
      if (mounted) setState(() => _paused = !_paused);
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    }
  }

  Future<void> _stop() async {
    try {
      final path = await ref.read(recorderServiceProvider).stop();
      _timer?.cancel();
      if (mounted) {
        setState(() {
          _path = path;
          _recording = false;
          _paused = false;
        });
        await _analyzeLocal();
      }
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    }
  }

  Future<void> _pick() async {
    try {
      final path = await ref.read(documentPickerProvider).pickAny();
      if (path == null) return;
      setState(() {
        _path = path;
        _ownedFile = false;
        _recording = false;
        _paused = false;
        _localAnalysis = null;
        _serverReference = null;
        _transcript = null;
        _processedResult = null;
      });
      await _analyzeLocal();
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    }
  }

  Future<void> _delete() async {
    _timer?.cancel();
    final selected = _path;
    final recorder = ref.read(recorderServiceProvider);
    if (_recording || _paused || _ownedFile) {
      if (selected != null && recorder.path != selected && _ownedFile) {
        final file = File(selected);
        if (await file.exists()) await file.delete();
      }
      await recorder.delete();
    }
    setState(() {
      _path = null;
      _ownedFile = false;
      _recording = false;
      _paused = false;
      _elapsedSeconds = 0;
      _localAnalysis = null;
      _serverReference = null;
      _transcript = null;
      _processedResult = null;
    });
  }

  Future<void> _analyzeLocal() async {
    final path = _path;
    if (path == null) return;
    setState(() => _busy = true);
    try {
      final analysis = await ref.read(localAudioServiceProvider).analyze(path);
      ref.read(selectedReferenceProvider.notifier).state = SelectedReference(
        localPath: path,
        fileId: '',
        analysis: analysis,
      );
      if (mounted) setState(() => _localAnalysis = analysis);
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _convert() async {
    final path = _path;
    if (path == null) return;
    setState(() => _busy = true);
    try {
      final converted =
          await ref.read(localAudioServiceProvider).convertToWav(path);
      setState(() {
        _path = converted;
        _ownedFile = true;
        _localAnalysis = null;
        _processedResult = <String, dynamic>{
          'local_path': converted,
          'name': p.basename(converted),
          'engine': 'ffmpeg-local-convert',
        };
      });
      await _analyzeLocal();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('تم التحويل محليًا إلى WAV بجودة 24 kHz.'),
          ),
        );
      }
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _analyzeOnServer() async {
    final path = _path;
    if (path == null) return;
    if (ref.read(appControllerProvider).session == null) {
      showArabicError(
        context,
        'التحليل المحلي جاهز ولا يحتاج ربطًا. الرفع الدقيق اختياري ويتطلب خادمًا.',
      );
      return;
    }
    setState(() {
      _busy = true;
      _uploadProgress = 0;
      _uploadCancelToken = CancelToken();
    });
    try {
      final fileSize = await File(path).length();
      final api = ref.read(apiServiceProvider);
      final SelectedReference reference;
      if (fileSize > 5 * 1024 * 1024) {
        final fileId = await api.uploadResumable(
          path,
          cancelToken: _uploadCancelToken,
          onProgress: (sent, total) {
            if (mounted) {
              setState(() => _uploadProgress = total > 0 ? sent / total : null);
            }
          },
        );
        reference = await api.analyzeReferenceId(fileId, path);
      } else {
        reference = await api.analyzeReference(
          path,
          cancelToken: _uploadCancelToken,
          onProgress: (sent, total) {
            if (mounted) {
              setState(() => _uploadProgress = total > 0 ? sent / total : null);
            }
          },
        );
      }
      ref.read(selectedReferenceProvider.notifier).state = reference;
      if (mounted) setState(() => _serverReference = reference);
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _uploadProgress = null;
          _uploadCancelToken = null;
        });
      }
    }
  }

  Future<void> _play() async {
    final path = _path;
    if (path == null) return;
    try {
      await ref.read(playerServiceProvider).playFile(path);
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    }
  }

  Future<void> _transcribe() async {
    final path = _path;
    if (path == null) return;
    if (!_cloudConfig.hasGemini) {
      showArabicError(
        context,
        'أضف مفتاح Gemini من الإعدادات لتحويل الصوت إلى نص مباشرة من الهاتف.',
      );
      return;
    }
    setState(() {
      _busy = true;
      _cloudProgress = 0;
      _transcript = null;
    });
    _cloudCancelToken = CancelToken();
    try {
      final transcript =
          await ref.read(cloudProviderServiceProvider).transcribeGemini(
                apiKey: _cloudConfig.geminiApiKey,
                model: _cloudConfig.geminiTextModel,
                audioPath: path,
                cancelToken: _cloudCancelToken,
                onProgress: (sent, total) {
                  if (mounted && total > 0) {
                    setState(() => _cloudProgress = sent / total);
                  }
                },
              );
      if (mounted) setState(() => _transcript = transcript);
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      _cloudCancelToken = null;
      if (mounted) {
        setState(() {
          _busy = false;
          _cloudProgress = null;
        });
      }
    }
  }

  Future<void> _applyEffect() async {
    final path = _path;
    if (path == null) return;
    setState(() => _busy = true);
    try {
      final output = await ref
          .read(localAudioServiceProvider)
          .applyEffect(path, _effectPreset);
      if (!mounted) return;
      setState(() {
        _path = output;
        _ownedFile = true;
        _localAnalysis = null;
        _processedResult = <String, dynamic>{
          'local_path': output,
          'name': p.basename(output),
          'engine': 'ffmpeg-local-effect',
        };
      });
      await _analyzeLocal();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('تم تطبيق المؤثر وحفظ نسخة جديدة.')),
        );
      }
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _trim() async {
    final path = _path;
    if (path == null) return;
    final start = double.tryParse(_trimStartController.text.trim()) ?? -1;
    final end = double.tryParse(_trimEndController.text.trim()) ?? -1;
    if (start < 0 || end < 0) {
      showArabicError(context, 'أدخل قيم قص صحيحة بالثواني.');
      return;
    }
    setState(() => _busy = true);
    try {
      final output = await ref.read(localAudioServiceProvider).trim(
            inputPath: path,
            removeStartSeconds: start,
            removeEndSeconds: end,
          );
      if (!mounted) return;
      setState(() {
        _path = output;
        _ownedFile = true;
        _localAnalysis = null;
        _processedResult = <String, dynamic>{
          'local_path': output,
          'name': p.basename(output),
          'engine': 'ffmpeg-local-trim',
        };
      });
      await _analyzeLocal();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('تم قص الملف وحفظ نسخة جديدة.')),
        );
      }
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _changeVoice() async {
    final path = _path;
    if (path == null) return;
    if (!_cloudConfig.hasElevenLabs) {
      showArabicError(
        context,
        'أضف مفتاح ElevenLabs من الإعدادات لتشغيل مغير الصوت مباشرة.',
      );
      return;
    }
    if (_selectedElevenVoice.isEmpty) {
      showArabicError(context, 'حمّل أصوات ElevenLabs واختر الصوت المطلوب.');
      return;
    }
    setState(() {
      _busy = true;
      _cloudProgress = 0;
    });
    _cloudCancelToken = CancelToken();
    try {
      final output =
          await ref.read(cloudProviderServiceProvider).changeVoiceElevenLabs(
                apiKey: _cloudConfig.elevenLabsApiKey,
                model: _cloudConfig.elevenLabsStsModel,
                voiceId: _selectedElevenVoice,
                sourcePath: path,
                removeBackgroundNoise: _removeVoiceNoise,
                cancelToken: _cloudCancelToken,
                onSendProgress: (sent, total) {
                  if (mounted && total > 0) {
                    setState(() => _cloudProgress = sent / total);
                  }
                },
              );
      if (!mounted) return;
      setState(() {
        _path = output;
        _ownedFile = true;
        _localAnalysis = null;
        _processedResult = <String, dynamic>{
          'local_path': output,
          'name': p.basename(output),
          'engine': 'elevenlabs-voice-changer',
        };
      });
      await _analyzeLocal();
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      _cloudCancelToken = null;
      if (mounted) {
        setState(() {
          _busy = false;
          _cloudProgress = null;
        });
      }
    }
  }

  void _cancelUpload() {
    _uploadCancelToken?.cancel('ألغى المستخدم عملية الرفع');
  }

  @override
  Widget build(BuildContext context) {
    final selectedPath = _path;
    final hasServer = ref.watch(
      appControllerProvider.select((state) => state.session != null),
    );
    final supportedFormats = AppConstants.supportedAudioExtensions
        .map((value) => value.toUpperCase())
        .join('، ');
    return ResponsivePage(
      children: <Widget>[
        SectionCard(
          title: 'التسجيل والملفات الصوتية',
          icon: Icons.mic_rounded,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              if (_recording)
                Column(
                  children: <Widget>[
                    Icon(
                      _paused
                          ? Icons.pause_circle_filled_rounded
                          : Icons.fiber_manual_record_rounded,
                      size: 72,
                      color: _paused ? Colors.orange : Colors.red,
                    ),
                    Text(
                      formatDuration(Duration(seconds: _elapsedSeconds)),
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    Text(
                      _paused
                          ? 'التسجيل متوقف مؤقتًا ويمكن استكماله'
                          : 'جارٍ التسجيل من الميكروفون',
                    ),
                  ],
                )
              else if (selectedPath != null)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const CircleAvatar(
                    child: Icon(Icons.audio_file_rounded),
                  ),
                  title: Text(p.basename(selectedPath)),
                  subtitle: FutureBuilder<int>(
                    future: File(selectedPath).length(),
                    builder: (context, snapshot) => Text(
                      snapshot.hasData
                          ? formatBytes(snapshot.data!)
                          : 'جارٍ قراءة الحجم...',
                    ),
                  ),
                )
              else
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 24),
                  child: Text(
                    'سجّل مباشرة أو اختر أي ملف يستطيع FFmpeg فكّه، بما في ذلك $supportedFormats.',
                    textAlign: TextAlign.center,
                  ),
                ),
              const SizedBox(height: 12),
              Wrap(
                alignment: WrapAlignment.center,
                spacing: 10,
                runSpacing: 10,
                children: <Widget>[
                  if (!_recording && selectedPath == null)
                    FilledButton.icon(
                      onPressed: _start,
                      icon: const Icon(Icons.mic_rounded),
                      label: const Text('بدء التسجيل'),
                    ),
                  if (_recording)
                    FilledButton.tonalIcon(
                      onPressed: _pauseOrResume,
                      icon: Icon(
                        _paused
                            ? Icons.play_arrow_rounded
                            : Icons.pause_rounded,
                      ),
                      label: Text(_paused ? 'استكمال' : 'إيقاف مؤقت'),
                    ),
                  if (_recording)
                    FilledButton.icon(
                      onPressed: _stop,
                      icon: const Icon(Icons.stop_rounded),
                      label: const Text('إنهاء التسجيل'),
                    ),
                  if (!_recording)
                    OutlinedButton.icon(
                      onPressed: _busy ? null : _pick,
                      icon: const Icon(Icons.folder_open_rounded),
                      label: const Text('اختيار ملف'),
                    ),
                  if (selectedPath != null && !_recording)
                    OutlinedButton.icon(
                      onPressed: _play,
                      icon: const Icon(Icons.play_arrow_rounded),
                      label: const Text('معاينة'),
                    ),
                  if (selectedPath != null)
                    OutlinedButton.icon(
                      onPressed: _delete,
                      icon: const Icon(Icons.delete_outline_rounded),
                      label: Text(
                        _ownedFile ? 'حذف التسجيل' : 'إزالة الاختيار',
                      ),
                    ),
                ],
              ),
              if (_busy)
                const Padding(
                  padding: EdgeInsets.only(top: 14),
                  child: LinearProgressIndicator(),
                ),
              if (_uploadProgress != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Column(
                    children: <Widget>[
                      Text(
                        'رفع الملف: ${(_uploadProgress! * 100).toStringAsFixed(0)}٪',
                        textAlign: TextAlign.center,
                      ),
                      TextButton.icon(
                        onPressed: _cancelUpload,
                        icon: const Icon(Icons.cancel_outlined),
                        label: const Text('إلغاء الرفع'),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        if (_localAnalysis != null) ...<Widget>[
          const SizedBox(height: 12),
          AudioAnalysisCard(analysis: _localAnalysis!),
        ],
        if (selectedPath != null && !_recording) ...<Widget>[
          const SizedBox(height: 12),
          SectionCard(
            title: 'المعالجة',
            icon: Icons.tune_rounded,
            child: Wrap(
              spacing: 10,
              runSpacing: 10,
              children: <Widget>[
                FilledButton.tonalIcon(
                  onPressed: _busy ? null : _analyzeLocal,
                  icon: const Icon(Icons.phone_android_rounded),
                  label: const Text('تحليل محلي'),
                ),
                FilledButton.tonalIcon(
                  onPressed: _busy ? null : _transcribe,
                  icon: const Icon(Icons.transcribe_rounded),
                  label: Text(
                    _cloudConfig.hasGemini
                        ? 'تحويل إلى نص عبر Gemini'
                        : 'تحويل إلى نص — أضف مفتاح Gemini',
                  ),
                ),
                FilledButton.tonalIcon(
                  onPressed: _busy ? null : _convert,
                  icon: const Icon(Icons.transform_rounded),
                  label: const Text('تحويل محلي إلى WAV'),
                ),
                if (hasServer)
                  FilledButton.icon(
                    onPressed: _busy ? null : _analyzeOnServer,
                    icon: const Icon(Icons.cloud_upload_rounded),
                    label: const Text('رفع وتحليل دقيق اختياري'),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          SectionCard(
            title: 'المؤثرات والمحرر المحلي',
            icon: Icons.auto_fix_high_rounded,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                DropdownButtonFormField<String>(
                  initialValue: _effectPreset,
                  decoration: const InputDecoration(labelText: 'المؤثر الجاهز'),
                  items: const <DropdownMenuItem<String>>[
                    DropdownMenuItem(
                      value: 'studio',
                      child: Text('صوت استوديو'),
                    ),
                    DropdownMenuItem(
                      value: 'lecture',
                      child: Text('محاضرة واضحة'),
                    ),
                    DropdownMenuItem(value: 'mosque', child: Text('صدى مسجد')),
                    DropdownMenuItem(
                      value: 'deep_voice',
                      child: Text('صوت عميق'),
                    ),
                    DropdownMenuItem(value: 'podcast', child: Text('بودكاست')),
                    DropdownMenuItem(
                      value: 'video_commentary',
                      child: Text('تعليق فيديو'),
                    ),
                  ],
                  onChanged: (value) =>
                      setState(() => _effectPreset = value ?? 'studio'),
                ),
                const SizedBox(height: 10),
                FilledButton.tonalIcon(
                  onPressed: _busy ? null : _applyEffect,
                  icon: const Icon(Icons.graphic_eq_rounded),
                  label: const Text('تطبيق المؤثر محليًا'),
                ),
                const Divider(height: 28),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: TextField(
                        controller: _trimStartController,
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                        ),
                        decoration: const InputDecoration(
                          labelText: 'حذف من البداية (ثانية)',
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        controller: _trimEndController,
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                        ),
                        decoration: const InputDecoration(
                          labelText: 'حذف من النهاية (ثانية)',
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  onPressed: _busy ? null : _trim,
                  icon: const Icon(Icons.content_cut_rounded),
                  label: const Text('قص وحفظ نسخة جديدة'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          SectionCard(
            title: 'مغير الصوت عبر ElevenLabs',
            icon: Icons.multitrack_audio_rounded,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                if (_cloudVoices.isEmpty)
                  OutlinedButton.icon(
                    onPressed: _loadCloudConfig,
                    icon: const Icon(Icons.refresh_rounded),
                    label: Text(
                      _cloudConfig.hasElevenLabs
                          ? 'تحميل أصوات ElevenLabs'
                          : 'أضف مفتاح ElevenLabs ثم حدّث',
                    ),
                  )
                else
                  DropdownButtonFormField<String>(
                    initialValue: _cloudVoices.any(
                      (voice) => voice.id == _selectedElevenVoice,
                    )
                        ? _selectedElevenVoice
                        : _cloudVoices.first.id,
                    isExpanded: true,
                    decoration: const InputDecoration(
                      labelText: 'الصوت الهدف',
                    ),
                    items: _cloudVoices
                        .map(
                          (voice) => DropdownMenuItem<String>(
                            value: voice.id,
                            child: Text(
                              voice.name,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        )
                        .toList(),
                    onChanged: (value) =>
                        setState(() => _selectedElevenVoice = value ?? ''),
                  ),
                SwitchListTile(
                  value: _removeVoiceNoise,
                  contentPadding: EdgeInsets.zero,
                  title: const Text('تنقية الضوضاء قبل تغيير الصوت'),
                  onChanged: (value) =>
                      setState(() => _removeVoiceNoise = value),
                ),
                FilledButton.tonalIcon(
                  onPressed: _busy ? null : _changeVoice,
                  icon: const Icon(Icons.record_voice_over_rounded),
                  label: const Text('تغيير الصوت مباشرة'),
                ),
              ],
            ),
          ),
        ],
        if (_cloudProgress != null) ...<Widget>[
          const SizedBox(height: 12),
          LinearProgressIndicator(value: _cloudProgress),
          TextButton.icon(
            onPressed: () => _cloudCancelToken?.cancel(),
            icon: const Icon(Icons.cancel_rounded),
            label: const Text('إلغاء تحويل الصوت إلى نص'),
          ),
        ],
        if (_transcript != null) ...<Widget>[
          const SizedBox(height: 12),
          SectionCard(
            title: 'النص المستخرج',
            icon: Icons.article_rounded,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                SelectableText(_transcript!),
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: _transcript!));
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('تم نسخ النص.')),
                    );
                  },
                  icon: const Icon(Icons.copy_rounded),
                  label: const Text('نسخ النص'),
                ),
              ],
            ),
          ),
        ],
        if (_processedResult != null) ...<Widget>[
          const SizedBox(height: 12),
          AudioResultList(result: _processedResult!),
        ],
        if (_localAnalysis != null) ...<Widget>[
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: () => context.go('/clone'),
            icon: const Icon(Icons.record_voice_over_rounded),
            label: const Text('استخدامه في استنساخ الصوت Pro'),
          ),
        ],
        if (_serverReference != null) ...<Widget>[
          const SizedBox(height: 12),
          AudioAnalysisCard(analysis: _serverReference!.analysis),
        ],
        const SizedBox(height: 90),
      ],
    );
  }
}
