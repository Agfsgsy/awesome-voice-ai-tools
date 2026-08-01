import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/cloud_provider_models.dart';
import 'package:voice_ai_mobile/services/cloud_provider_service.dart';
import 'package:voice_ai_mobile/widgets/audio_result_list.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';
import 'package:voice_ai_mobile/widgets/tracked_jobs_panel.dart';

class SongStudioScreen extends ConsumerStatefulWidget {
  const SongStudioScreen({super.key});

  @override
  ConsumerState<SongStudioScreen> createState() => _SongStudioScreenState();
}

class _SongStudioScreenState extends ConsumerState<SongStudioScreen> {
  final _titleController = TextEditingController();
  final _lyricsController = TextEditingController();
  final _voiceController = TextEditingController(text: 'default');
  String _style = 'شيلة عربية';
  String _engine = 'local';
  int _candidates = 3;
  double _tempo = 1;
  double _pitch = 0;
  double _reverb = 0.25;
  String? _instrumentalPath;
  String? _instrumentalFileId;
  bool _busy = false;
  double? _uploadProgress;
  double? _cloudProgress;
  String? _jobId;
  Map<String, dynamic>? _result;
  CancelToken? _cancelToken;
  List<CloudVoice> _cloudVoices = const <CloudVoice>[];
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
    Future<void>.microtask(_loadCloudProviders);
  }

  @override
  void dispose() {
    _titleController.dispose();
    _lyricsController.dispose();
    _voiceController.dispose();
    _cancelToken?.cancel();
    super.dispose();
  }

  Future<void> _loadCloudProviders() async {
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
        });
      }
    } on Object {
      // تظهر رسالة الإعداد المطلوبة عند تشغيل المزود.
    }
  }

  Future<void> _pickInstrumental() async {
    try {
      final path = await ref.read(documentPickerProvider).pickAny();
      if (path != null) {
        setState(() {
          _instrumentalPath = path;
          _instrumentalFileId = null;
        });
      }
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    }
  }

  Future<String?> _uploadInstrumental() async {
    if (_instrumentalPath == null) return null;
    if (_instrumentalFileId != null) return _instrumentalFileId;
    final id = await ref
        .read(apiServiceProvider)
        .uploadResumable(
          _instrumentalPath!,
          onProgress: (sent, total) {
            if (mounted) {
              setState(() => _uploadProgress = total > 0 ? sent / total : null);
            }
          },
        );
    _instrumentalFileId = id;
    return id;
  }

  Future<void> _generate() async {
    if (_titleController.text.trim().isEmpty ||
        _lyricsController.text.trim().isEmpty) {
      showArabicError(context, 'أدخل عنوان المشروع وكلمات الشيلة أو الأغنية.');
      return;
    }
    setState(() {
      _busy = true;
      _result = null;
      _jobId = null;
      _cloudProgress = null;
    });
    _cancelToken = CancelToken();
    try {
      if (_engine == 'local') {
        final vocal = await ref
            .read(localTtsServiceProvider)
            .synthesizeToFile(_lyricsController.text.trim(), speed: _tempo);
        final output = await ref
            .read(localAudioServiceProvider)
            .createSongMix(
              vocalPath: vocal,
              title: _titleController.text.trim(),
              instrumentalPath: _instrumentalPath,
              tempo: 1,
              pitchSemitones: _pitch,
              reverb: _reverb,
            );
        if (mounted) {
          setState(
            () => _result = <String, dynamic>{
              'local_path': output,
              'name': p.basename(output),
              'engine': 'android-local-song',
            },
          );
        }
        return;
      }
      if (_engine == 'gemini_direct' || _engine == 'elevenlabs_direct') {
        final isGemini = _engine == 'gemini_direct';
        final cloudResult = await ref
            .read(cloudProviderServiceProvider)
            .synthesizeCandidates(
              provider: _engine,
              apiKey: isGemini
                  ? _cloudConfig.geminiApiKey
                  : _cloudConfig.elevenLabsApiKey,
              model: isGemini
                  ? _cloudConfig.geminiModel
                  : _cloudConfig.elevenLabsModel,
              voice: _voiceController.text.trim(),
              text: _lyricsController.text.trim(),
              candidateCount: _candidates,
              style: isGemini
                  ? '$_style، أداء لحني وإيقاعي عربي احترافي مع نطق واضح للكلمات'
                  : null,
              cancelToken: _cancelToken,
              onProgress: (completed, total) {
                if (mounted) {
                  setState(() => _cloudProgress = completed / (total * 2));
                }
              },
            );
        final vocals =
            (cloudResult['candidates'] as List<dynamic>? ?? const <dynamic>[])
                .whereType<Map<String, dynamic>>()
                .toList();
        final mixed = <Map<String, dynamic>>[];
        for (var index = 0; index < vocals.length; index++) {
          if (_cancelToken?.isCancelled == true) {
            throw const AppException('المهمة أُلغيت.', code: 'cancelled');
          }
          final vocalPath = vocals[index]['local_path'] as String?;
          if (vocalPath == null || vocalPath.isEmpty) {
            throw const AppException('الملف الناتج غير صالح.');
          }
          final output = await ref
              .read(localAudioServiceProvider)
              .createSongMix(
                vocalPath: vocalPath,
                title: '${_titleController.text.trim()}_${index + 1}',
                instrumentalPath: _instrumentalPath,
                tempo: _tempo,
                pitchSemitones: _pitch,
                reverb: _reverb,
              );
          mixed.add(<String, dynamic>{
            'candidate_id': 'song_${index + 1}',
            'local_path': output,
            'name': p.basename(output),
            'provider': _engine,
          });
          if (mounted) {
            setState(
              () => _cloudProgress = 0.5 + ((index + 1) / (vocals.length * 2)),
            );
          }
        }
        if (mixed.isEmpty) {
          throw const AppException('لم يتم إنشاء أي نتيجة صوتية صالحة.');
        }
        if (mounted) {
          setState(
            () => _result = <String, dynamic>{
              'candidates': mixed,
              'best_candidate_id': mixed.first['candidate_id'],
              'engine': _engine,
            },
          );
        }
        return;
      }
      if (ref.read(appControllerProvider).session == null) {
        throw const AppException(
          'المحرك المختار يحتاج خادمًا اختياريًا. اختر «استوديو الهاتف» للعمل دون ربط.',
        );
      }
      final headers = await ref.read(providerHeadersProvider.future);
      final instrumentalId = await _uploadInstrumental();
      final job = await ref
          .read(apiServiceProvider)
          .generateSong(
            title: _titleController.text.trim(),
            lyrics: _lyricsController.text.trim(),
            style: _style,
            engine: _engine,
            voice: _voiceController.text.trim().isEmpty
                ? 'default'
                : _voiceController.text.trim(),
            candidateCount: _candidates,
            tempo: _tempo,
            pitch: _pitch,
            reverb: _reverb,
            instrumentalFileId: instrumentalId,
            providerHeaders: headers,
          );
      await ref.read(jobControllerProvider.notifier).track(job);
      if (mounted) setState(() => _jobId = job.id);
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      _cancelToken = null;
      if (mounted) {
        setState(() {
          _busy = false;
          _uploadProgress = null;
          _cloudProgress = null;
        });
      }
    }
  }

  void _selectEngine(String? value) {
    final engine = value ?? 'local';
    setState(() {
      _engine = engine;
      if (engine == 'gemini_direct') {
        _voiceController.text = _cloudConfig.geminiVoice;
      } else if (engine == 'elevenlabs_direct') {
        _voiceController.text = _cloudVoices.isEmpty
            ? ''
            : _cloudVoices.first.id;
      } else if (engine == 'local') {
        _voiceController.text = 'default';
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final localSelected = _engine == 'local';
    final geminiSelected = _engine == 'gemini_direct';
    final elevenLabsSelected = _engine == 'elevenlabs_direct';
    final directCloudSelected = geminiSelected || elevenLabsSelected;
    final hasServer = ref.watch(
      appControllerProvider.select((state) => state.session != null),
    );
    return ResponsivePage(
      children: <Widget>[
        Card(
          color: Theme.of(context).colorScheme.primaryContainer,
          child: ListTile(
            leading: const Icon(Icons.offline_bolt_rounded),
            title: const Text('استوديو الهاتف المحلي'),
            subtitle: const Text(
              'يولّد الأداء محليًا أو مباشرة عبر Gemini وElevenLabs، ثم يطبّق السرعة والطبقة والصدى والمزج على الهاتف بواسطة FFmpeg.',
            ),
            trailing: TextButton(
              onPressed: () =>
                  ref.read(localTtsServiceProvider).installVoiceData(),
              child: const Text('تنزيل العربية'),
            ),
          ),
        ),
        const SizedBox(height: 12),
        SectionCard(
          title: 'استوديو الشيلات والأغاني',
          icon: Icons.library_music_rounded,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              TextField(
                controller: _titleController,
                decoration: const InputDecoration(labelText: 'اسم المشروع'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _lyricsController,
                minLines: 8,
                maxLines: 18,
                decoration: const InputDecoration(
                  labelText: 'الكلمات',
                  hintText: 'اكتب الأبيات أو كلمات الأغنية هنا...',
                ),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: <Widget>[
                  SizedBox(
                    width: 270,
                    child: DropdownButtonFormField<String>(
                      initialValue: _style,
                      decoration: const InputDecoration(labelText: 'النمط'),
                      items:
                          const <String>[
                                'شيلة عربية',
                                'شيلة حماسية',
                                'شيلة هادئة',
                                'أغنية عربية',
                                'إنشاد دون موسيقى',
                              ]
                              .map(
                                (value) => DropdownMenuItem(
                                  value: value,
                                  child: Text(value),
                                ),
                              )
                              .toList(),
                      onChanged: (value) =>
                          setState(() => _style = value ?? 'شيلة عربية'),
                    ),
                  ),
                  SizedBox(
                    width: 270,
                    child: DropdownButtonFormField<String>(
                      initialValue: _engine,
                      decoration: const InputDecoration(labelText: 'المحرك'),
                      items: <DropdownMenuItem<String>>[
                        const DropdownMenuItem(
                          value: 'local',
                          child: Text('استوديو الهاتف — دون إنترنت'),
                        ),
                        DropdownMenuItem(
                          value: 'gemini_direct',
                          child: Text(
                            _cloudConfig.hasGemini
                                ? 'Gemini TTS — مباشر'
                                : 'Gemini TTS — يحتاج مفتاحًا',
                          ),
                        ),
                        DropdownMenuItem(
                          value: 'elevenlabs_direct',
                          child: Text(
                            _cloudConfig.hasElevenLabs
                                ? 'ElevenLabs — مباشر'
                                : 'ElevenLabs — يحتاج مفتاحًا',
                          ),
                        ),
                        if (hasServer)
                          const DropdownMenuItem(
                            value: 'auto',
                            child: Text('خادم — اختيار تلقائي'),
                          ),
                        if (hasServer)
                          const DropdownMenuItem(
                            value: 'xtts',
                            child: Text('XTTS على الخادم'),
                          ),
                        if (hasServer)
                          const DropdownMenuItem(
                            value: 'elevenlabs',
                            child: Text('ElevenLabs عبر الخادم'),
                          ),
                        if (hasServer)
                          const DropdownMenuItem(
                            value: 'gemini',
                            child: Text('Gemini TTS عبر الخادم'),
                          ),
                      ],
                      onChanged: _selectEngine,
                    ),
                  ),
                  if (geminiSelected)
                    SizedBox(
                      width: 270,
                      child: DropdownButtonFormField<String>(
                        initialValue:
                            CloudProviderService.geminiVoices.contains(
                              _voiceController.text,
                            )
                            ? _voiceController.text
                            : _cloudConfig.geminiVoice,
                        decoration: const InputDecoration(
                          labelText: 'صوت Gemini',
                        ),
                        items: CloudProviderService.geminiVoices
                            .map(
                              (voice) => DropdownMenuItem<String>(
                                value: voice,
                                child: Text(voice),
                              ),
                            )
                            .toList(),
                        onChanged: (value) => setState(
                          () => _voiceController.text = value ?? 'Kore',
                        ),
                      ),
                    )
                  else if (elevenLabsSelected)
                    SizedBox(
                      width: 270,
                      child: _cloudVoices.isEmpty
                          ? OutlinedButton.icon(
                              onPressed: _loadCloudProviders,
                              icon: const Icon(Icons.refresh_rounded),
                              label: const Text('تحميل أصوات ElevenLabs'),
                            )
                          : DropdownButtonFormField<String>(
                              initialValue:
                                  _cloudVoices.any(
                                    (voice) =>
                                        voice.id == _voiceController.text,
                                  )
                                  ? _voiceController.text
                                  : _cloudVoices.first.id,
                              decoration: const InputDecoration(
                                labelText: 'صوت ElevenLabs',
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
                              onChanged: (value) => setState(
                                () => _voiceController.text = value ?? '',
                              ),
                            ),
                    )
                  else if (!localSelected)
                    SizedBox(
                      width: 270,
                      child: TextField(
                        controller: _voiceController,
                        decoration: const InputDecoration(labelText: 'الصوت'),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              Card.filled(
                child: ListTile(
                  leading: const Icon(Icons.piano_rounded),
                  title: Text(
                    _instrumentalPath == null
                        ? 'مسار موسيقي اختياري'
                        : p.basename(_instrumentalPath!),
                  ),
                  subtitle: const Text('يمكن تركه فارغًا للإنشاد دون موسيقى'),
                  trailing: IconButton(
                    onPressed: _pickInstrumental,
                    icon: const Icon(Icons.folder_open_rounded),
                  ),
                ),
              ),
              if (_uploadProgress != null)
                LinearProgressIndicator(value: _uploadProgress),
              if (_cloudProgress != null)
                LinearProgressIndicator(value: _cloudProgress),
              const SizedBox(height: 12),
              Text('الإيقاع: ${_tempo.toStringAsFixed(2)}×'),
              Slider(
                value: _tempo,
                min: 0.5,
                max: 2,
                divisions: 30,
                onChanged: (value) => setState(() => _tempo = value),
              ),
              Text('طبقة الصوت: ${_pitch.toStringAsFixed(1)} نصف درجة'),
              Slider(
                value: _pitch,
                min: -6,
                max: 6,
                divisions: 24,
                onChanged: (value) => setState(() => _pitch = value),
              ),
              Text('الصدى: ${(_reverb * 100).round()}٪'),
              Slider(
                value: _reverb,
                max: 1,
                divisions: 20,
                onChanged: (value) => setState(() => _reverb = value),
              ),
              if (!localSelected) ...<Widget>[
                Text('عدد المرشحين: $_candidates'),
                Slider(
                  value: _candidates.toDouble(),
                  min: 1,
                  max: 5,
                  divisions: 4,
                  onChanged: (value) =>
                      setState(() => _candidates = value.round()),
                ),
              ],
              Row(
                children: <Widget>[
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: _busy ? null : _generate,
                      icon: _busy
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.auto_awesome_rounded),
                      label: Text(
                        localSelected
                            ? 'إنشاء المشروع على الهاتف'
                            : (directCloudSelected
                                  ? 'إنشاء مباشر ومزج على الهاتف'
                                  : 'إنشاء المشروع من الخادم'),
                      ),
                    ),
                  ),
                  if (_busy && directCloudSelected) ...<Widget>[
                    const SizedBox(width: 8),
                    IconButton.filledTonal(
                      tooltip: 'إلغاء المهمة',
                      onPressed: () => _cancelToken?.cancel(),
                      icon: const Icon(Icons.cancel_rounded),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
        if (_jobId != null) ...<Widget>[
          const SizedBox(height: 12),
          TrackedJobsPanel(
            onlyJobId: _jobId,
            onCompleted: (job) {
              if (_result == null && job.result != null) {
                setState(() => _result = job.result);
              }
            },
          ),
        ],
        if (_result != null) ...<Widget>[
          const SizedBox(height: 12),
          AudioResultList(result: _result!),
        ],
        const SizedBox(height: 90),
      ],
    );
  }
}
