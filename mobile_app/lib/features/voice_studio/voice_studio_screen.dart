import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/cloud_provider_models.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/services/cloud_provider_service.dart';
import 'package:voice_ai_mobile/widgets/audio_result_list.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';
import 'package:voice_ai_mobile/widgets/tracked_jobs_panel.dart';

class VoiceStudioScreen extends ConsumerStatefulWidget {
  const VoiceStudioScreen({super.key});

  @override
  ConsumerState<VoiceStudioScreen> createState() => _VoiceStudioScreenState();
}

class _VoiceStudioScreenState extends ConsumerState<VoiceStudioScreen> {
  final _textController = TextEditingController();
  final _voiceController = TextEditingController(text: 'default');
  final _styleController = TextEditingController(
    text: 'بصوت عربي طبيعي وواضح وبأسلوب احترافي',
  );
  List<EngineInfo> _engines = const <EngineInfo>[];
  List<CloudVoice> _cloudVoices = const <CloudVoice>[];
  CloudProviderConfig _cloudConfig = const CloudProviderConfig(
    geminiApiKey: '',
    geminiModel: 'gemini-3.1-flash-tts-preview',
    geminiVoice: 'Kore',
    elevenLabsApiKey: '',
    elevenLabsModel: 'eleven_multilingual_v2',
  );
  String _engine = 'local';
  double _speed = 1;
  int _candidates = 2;
  bool _loading = false;
  String? _jobId;
  Map<String, dynamic>? _result;
  CancelToken? _cancelToken;
  double? _progress;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_loadEngines);
  }

  @override
  void dispose() {
    _textController.dispose();
    _voiceController.dispose();
    _styleController.dispose();
    _cancelToken?.cancel();
    super.dispose();
  }

  Future<void> _loadEngines() async {
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
      var engines = const <EngineInfo>[];
      if (ref.read(appControllerProvider).session != null) {
        engines = await ref.read(apiServiceProvider).engines();
      }
      if (mounted) {
        setState(() {
          _cloudConfig = config;
          _cloudVoices = voices;
          _engines = engines;
        });
      }
    } on Object {
      // تظهر رسالة دقيقة عند محاولة استخدام المحرك غير المجهز.
    }
  }

  Future<void> _generate() async {
    if (_textController.text.trim().isEmpty) {
      showArabicError(context, 'أدخل النص المراد تحويله إلى صوت.');
      return;
    }
    setState(() {
      _loading = true;
      _result = null;
      _jobId = null;
      _progress = null;
    });
    _cancelToken = CancelToken();
    try {
      if (_engine == 'local') {
        final output = await ref
            .read(localTtsServiceProvider)
            .synthesizeToFile(_textController.text.trim(), speed: _speed);
        if (mounted) {
          setState(
            () => _result = <String, dynamic>{
              'local_path': output,
              'name': p.basename(output),
              'engine': 'android-local',
            },
          );
        }
        return;
      }
      if (_engine == 'gemini_direct' || _engine == 'elevenlabs_direct') {
        final isGemini = _engine == 'gemini_direct';
        final apiKey = isGemini
            ? _cloudConfig.geminiApiKey
            : _cloudConfig.elevenLabsApiKey;
        final model = isGemini
            ? _cloudConfig.geminiModel
            : _cloudConfig.elevenLabsModel;
        final voice = _voiceController.text.trim().isEmpty
            ? (isGemini ? _cloudConfig.geminiVoice : '')
            : _voiceController.text.trim();
        final result = await ref
            .read(cloudProviderServiceProvider)
            .synthesizeCandidates(
              provider: _engine,
              apiKey: apiKey,
              model: model,
              voice: voice,
              text: _textController.text.trim(),
              candidateCount: _candidates,
              style: isGemini ? _styleController.text.trim() : null,
              cancelToken: _cancelToken,
              onProgress: (completed, total) {
                if (mounted) {
                  setState(() => _progress = completed / total);
                }
              },
            );
        if (mounted) setState(() => _result = result);
        return;
      }
      if (ref.read(appControllerProvider).session == null) {
        throw const AppException(
          'المحرك المختار يحتاج خادمًا اختياريًا. اختر «محرك الهاتف» للعمل دون ربط.',
        );
      }
      final headers = await ref.read(providerHeadersProvider.future);
      final job = await ref
          .read(apiServiceProvider)
          .synthesize(
            text: _textController.text.trim(),
            engine: _engine,
            voice: _voiceController.text.trim().isEmpty
                ? 'default'
                : _voiceController.text.trim(),
            speed: _speed,
            candidateCount: _candidates,
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
          _loading = false;
          _progress = null;
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
    final wordCount = _textController.text.trim().isEmpty
        ? 0
        : _textController.text.trim().split(RegExp(r'\s+')).length;
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
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: <Widget>[
                const Icon(Icons.offline_bolt_rounded),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'اختر محرك الهاتف للعمل دون إنترنت، أو Gemini وElevenLabs للعمل مباشرة من الهاتف عبر الإنترنت دون كمبيوتر.',
                  ),
                ),
                TextButton(
                  onPressed: () async {
                    await ref.read(localTtsServiceProvider).installVoiceData();
                  },
                  child: const Text('تنزيل العربية'),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        SectionCard(
          title: 'توليد الصوت (Voice Studio)',
          icon: Icons.graphic_eq_rounded,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              TextField(
                controller: _textController,
                minLines: 6,
                maxLines: 14,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(
                  labelText: 'النص العربي',
                  hintText: 'اكتب أو الصق النص هنا...',
                ),
              ),
              const SizedBox(height: 6),
              Text(
                '${_textController.text.length} حرف • $wordCount كلمة • نحو ${(wordCount / 2.2).ceil()} ثانية',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 14),
              LayoutBuilder(
                builder: (context, constraints) => Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: <Widget>[
                    SizedBox(
                      width: constraints.maxWidth > 620
                          ? (constraints.maxWidth - 12) / 2
                          : constraints.maxWidth,
                      child: DropdownButtonFormField<String>(
                        initialValue: _engine,
                        isExpanded: true,
                        decoration: const InputDecoration(labelText: 'المحرك'),
                        items: <DropdownMenuItem<String>>[
                          const DropdownMenuItem(
                            value: 'local',
                            child: Text('محرك الهاتف — دون إنترنت'),
                          ),
                          DropdownMenuItem(
                            value: 'gemini_direct',
                            child: Text(
                              _cloudConfig.hasGemini
                                  ? 'Gemini TTS — مباشر من الهاتف'
                                  : 'Gemini TTS — يحتاج مفتاحًا',
                            ),
                          ),
                          DropdownMenuItem(
                            value: 'elevenlabs_direct',
                            child: Text(
                              _cloudConfig.hasElevenLabs
                                  ? 'ElevenLabs — مباشر من الهاتف'
                                  : 'ElevenLabs — يحتاج مفتاحًا',
                            ),
                          ),
                          if (hasServer)
                            const DropdownMenuItem(
                              value: 'auto',
                              child: Text('خادم — اختيار تلقائي'),
                            ),
                          if (hasServer)
                            ..._engines.map(
                              (engine) => DropdownMenuItem(
                                value: engine.name,
                                child: Text(
                                  '${engine.label}${engine.ready ? '' : ' — غير جاهز'}',
                                ),
                              ),
                            ),
                        ],
                        onChanged: _selectEngine,
                      ),
                    ),
                    if (geminiSelected)
                      SizedBox(
                        width: constraints.maxWidth > 620
                            ? (constraints.maxWidth - 12) / 2
                            : constraints.maxWidth,
                        child: DropdownButtonFormField<String>(
                          initialValue:
                              CloudProviderService.geminiVoices.contains(
                                _voiceController.text,
                              )
                              ? _voiceController.text
                              : _cloudConfig.geminiVoice,
                          isExpanded: true,
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
                        width: constraints.maxWidth > 620
                            ? (constraints.maxWidth - 12) / 2
                            : constraints.maxWidth,
                        child: _cloudVoices.isEmpty
                            ? OutlinedButton.icon(
                                onPressed: () => _loadEngines(),
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
                                isExpanded: true,
                                decoration: const InputDecoration(
                                  labelText: 'صوت ElevenLabs',
                                ),
                                items: _cloudVoices
                                    .map(
                                      (voice) => DropdownMenuItem<String>(
                                        value: voice.id,
                                        child: Text(
                                          '${voice.name} — ${voice.category}',
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
                        width: constraints.maxWidth > 620
                            ? (constraints.maxWidth - 12) / 2
                            : constraints.maxWidth,
                        child: TextField(
                          controller: _voiceController,
                          decoration: const InputDecoration(
                            labelText: 'الصوت',
                            helperText: 'اسم الصوت في المحرك المختار',
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              if (geminiSelected) ...<Widget>[
                const SizedBox(height: 12),
                TextField(
                  controller: _styleController,
                  minLines: 2,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    labelText: 'أسلوب الأداء',
                    helperText:
                        'مثال: أسلوب حماسي، هادئ، وثائقي، أو قراءة قصصية.',
                  ),
                ),
              ],
              const SizedBox(height: 14),
              Text('السرعة: ${_speed.toStringAsFixed(1)}×'),
              Slider(
                value: _speed,
                min: 0.5,
                max: 2,
                divisions: 15,
                onChanged: (value) => setState(() => _speed = value),
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
              if (_progress != null) ...<Widget>[
                LinearProgressIndicator(value: _progress),
                const SizedBox(height: 8),
              ],
              Row(
                children: <Widget>[
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: _loading ? null : _generate,
                      icon: _loading
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.auto_awesome_rounded),
                      label: Text(
                        localSelected
                            ? 'إنشاء الصوت على الهاتف'
                            : (directCloudSelected
                                  ? 'توليد مباشر من الهاتف'
                                  : 'توليد الصوت من الخادم'),
                      ),
                    ),
                  ),
                  if (_loading) ...<Widget>[
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
