import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:path/path.dart' as p;
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/cloud_provider_models.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/widgets/audio_analysis_card.dart';
import 'package:voice_ai_mobile/widgets/audio_result_list.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';
import 'package:voice_ai_mobile/widgets/tracked_jobs_panel.dart';

class VoiceCloneScreen extends ConsumerStatefulWidget {
  const VoiceCloneScreen({super.key});

  @override
  ConsumerState<VoiceCloneScreen> createState() => _VoiceCloneScreenState();
}

class _VoiceCloneScreenState extends ConsumerState<VoiceCloneScreen> {
  final _textController = TextEditingController();
  final _statementController = TextEditingController();
  final _voiceNameController = TextEditingController(text: 'صوتي من الهاتف');
  bool _consent = false;
  bool _busy = false;
  String _rights = 'self';
  String _engine = 'elevenlabs_direct';
  String _selectedElevenVoice = '__new__';
  bool _removeBackgroundNoise = false;
  int _candidates = 3;
  double? _progress;
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
    Future<void>.microtask(_loadCloudProvider);
  }

  @override
  void dispose() {
    _textController.dispose();
    _statementController.dispose();
    _voiceNameController.dispose();
    _cancelToken?.cancel();
    super.dispose();
  }

  Future<void> _loadCloudProvider() async {
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
      final lastVoice = await ref
          .read(secureStorageProvider)
          .readSecret('elevenlabs_last_voice_id');
      if (mounted) {
        setState(() {
          _cloudConfig = config;
          _cloudVoices = voices;
          if (lastVoice != null &&
              voices.any((voice) => voice.id == lastVoice)) {
            _selectedElevenVoice = lastVoice;
          }
        });
      }
    } on Object {
      // تعرض الواجهة طريقة إضافة المفتاح عند التشغيل.
    }
  }

  Future<void> _chooseReference() async {
    try {
      final path = await ref.read(documentPickerProvider).pickAny();
      if (path == null) return;
      setState(() => _busy = true);
      if (_engine == 'elevenlabs_direct' ||
          ref.read(appControllerProvider).session == null) {
        final analysis = await ref
            .read(localAudioServiceProvider)
            .analyze(path);
        ref.read(selectedReferenceProvider.notifier).state = SelectedReference(
          localPath: path,
          fileId: '',
          analysis: analysis,
        );
        return;
      }
      final api = ref.read(apiServiceProvider);
      final fileSize = await File(path).length();
      final SelectedReference reference;
      if (fileSize > 5 * 1024 * 1024) {
        final fileId = await api.uploadResumable(path);
        reference = await api.analyzeReferenceId(fileId, path);
      } else {
        reference = await api.analyzeReference(path);
      }
      ref.read(selectedReferenceProvider.notifier).state = reference;
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _submit() async {
    final reference = ref.read(selectedReferenceProvider);
    if (reference == null) {
      showArabicError(context, 'سجّل صوتًا مرجعيًا أو اختر ملفًا وحلله أولًا.');
      return;
    }
    if (!reference.analysis.clearSpeech) {
      showArabicError(
        context,
        'التسجيل لا يحتوي كلامًا واضحًا؛ أعد التسجيل قبل الاستنساخ.',
      );
      return;
    }
    if (!_consent || _statementController.text.trim().length < 12) {
      showArabicError(
        context,
        'يجب تأكيد ملكية الصوت أو وجود إذن صريح وكتابة إقرار واضح.',
      );
      return;
    }
    if (_textController.text.trim().isEmpty) {
      showArabicError(context, 'أدخل النص المراد نطقه بالصوت المستنسخ.');
      return;
    }
    setState(() {
      _busy = true;
      _result = null;
      _jobId = null;
      _progress = 0;
    });
    _cancelToken = CancelToken();
    try {
      if (_engine == 'elevenlabs_direct') {
        if (!_cloudConfig.hasElevenLabs) {
          throw const AppException(
            'أضف مفتاح ElevenLabs من الإعدادات لتشغيل الاستنساخ مباشرة من الهاتف.',
          );
        }
        var voiceId = _selectedElevenVoice;
        if (voiceId == '__new__') {
          final cloned = await ref
              .read(cloudProviderServiceProvider)
              .cloneElevenLabsVoice(
                apiKey: _cloudConfig.elevenLabsApiKey,
                referencePath: reference.localPath,
                voiceName: _voiceNameController.text.trim(),
                rights: _rights,
                removeBackgroundNoise: _removeBackgroundNoise,
                cancelToken: _cancelToken,
                onSendProgress: (sent, total) {
                  if (mounted && total > 0) {
                    setState(() => _progress = (sent / total) * 0.35);
                  }
                },
              );
          voiceId = cloned.id;
          await ref
              .read(secureStorageProvider)
              .writeSecret('elevenlabs_last_voice_id', cloned.id);
          if (mounted) {
            setState(() {
              _cloudVoices = <CloudVoice>[cloned, ..._cloudVoices];
              _selectedElevenVoice = cloned.id;
            });
          }
        }
        final result = await ref
            .read(cloudProviderServiceProvider)
            .synthesizeCandidates(
              provider: 'elevenlabs_direct',
              apiKey: _cloudConfig.elevenLabsApiKey,
              model: _cloudConfig.elevenLabsModel,
              voice: voiceId,
              text: _textController.text.trim(),
              candidateCount: _candidates,
              cancelToken: _cancelToken,
              onProgress: (completed, total) {
                if (mounted) {
                  setState(() => _progress = 0.35 + (completed / total) * 0.65);
                }
              },
            );
        if (mounted) setState(() => _result = result);
        return;
      }
      if (ref.read(appControllerProvider).session == null) {
        throw const AppException(
          'XTTS وCoqui يحتاجان خادمًا اختياريًا. استخدم ElevenLabs المباشر للعمل من الهاتف دون ربط.',
        );
      }
      var serverReference = reference;
      if (serverReference.fileId.isEmpty) {
        final fileId = await ref
            .read(apiServiceProvider)
            .uploadResumable(reference.localPath);
        serverReference = await ref
            .read(apiServiceProvider)
            .analyzeReferenceId(fileId, reference.localPath);
        ref.read(selectedReferenceProvider.notifier).state = serverReference;
      }
      final job = await ref
          .read(apiServiceProvider)
          .cloneVoice(
            referenceFileId: serverReference.fileId,
            text: _textController.text.trim(),
            engine: _engine,
            candidateCount: _candidates,
            rights: _rights,
            consentStatement: _statementController.text.trim(),
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
          _progress = null;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final reference = ref.watch(selectedReferenceProvider);
    final hasServer = ref.watch(
      appControllerProvider.select((state) => state.session != null),
    );
    return ResponsivePage(
      children: <Widget>[
        Card(
          color: Theme.of(context).colorScheme.primaryContainer,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                const Text(
                  'استنساخ Pro مباشر من الهاتف',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 6),
                Text(
                  _cloudConfig.hasElevenLabs
                      ? 'ElevenLabs جاهز للاستنساخ والتوليد عبر الإنترنت دون كمبيوتر. التسجيل والتحليل والمعاينة تتم محليًا.'
                      : 'أضف مفتاح ElevenLabs في الإعدادات مرة واحدة؛ سيُحفظ مشفرًا في Android Keystore ثم يعمل الاستنساخ من الهاتف دون QR أو كمبيوتر.',
                ),
                if (!_cloudConfig.hasElevenLabs) ...<Widget>[
                  const SizedBox(height: 10),
                  FilledButton.icon(
                    onPressed: () => context.go('/settings'),
                    icon: const Icon(Icons.key_rounded),
                    label: const Text('فتح إعدادات المفاتيح'),
                  ),
                ],
                if (!hasServer) ...<Widget>[
                  const SizedBox(height: 8),
                  const Text(
                    'XTTS الكامل يبقى متاحًا عند إضافة خادم GPU اختياري، لأنه نموذج ثقيل لا يناسب ذاكرة أغلب الهواتف.',
                    style: TextStyle(fontSize: 12),
                  ),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Card(
          color: Colors.amber.withValues(alpha: 0.14),
          child: const Padding(
            padding: EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(Icons.verified_user_rounded, color: Colors.amber),
                SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'الموافقة إلزامية: لا يجوز استنساخ صوت أي شخص دون أن تكون صاحب الصوت أو تحمل إذنًا صريحًا منه. لا يبدأ التطبيق أي مهمة قبل تأكيد ذلك.',
                    style: TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        SectionCard(
          title: 'الصوت المرجعي',
          icon: Icons.audio_file_rounded,
          child: reference == null
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    const Text(
                      'اختر تسجيلًا واضحًا مدته ثانيتان على الأقل. سيُحلل قبل السماح بالاستنساخ.',
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: <Widget>[
                        FilledButton.tonalIcon(
                          onPressed: _busy ? null : () => context.go('/record'),
                          icon: const Icon(Icons.mic_rounded),
                          label: const Text('تسجيل وتحليل'),
                        ),
                        OutlinedButton.icon(
                          onPressed: _busy ? null : _chooseReference,
                          icon: const Icon(Icons.folder_open_rounded),
                          label: Text(
                            hasServer
                                ? 'اختيار ملف وتحليله'
                                : 'اختيار ملف وتحليله محليًا',
                          ),
                        ),
                      ],
                    ),
                  ],
                )
              : ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const CircleAvatar(child: Icon(Icons.check_rounded)),
                  title: Text(p.basename(reference.localPath)),
                  subtitle: Text(
                    'جودة ${reference.analysis.qualityScore}/100 • ${reference.analysis.durationSeconds.toStringAsFixed(1)} ثانية',
                  ),
                  trailing: IconButton(
                    tooltip: 'تغيير الملف',
                    onPressed: _chooseReference,
                    icon: const Icon(Icons.swap_horiz_rounded),
                  ),
                ),
        ),
        if (reference != null) ...<Widget>[
          const SizedBox(height: 12),
          AudioAnalysisCard(analysis: reference.analysis),
        ],
        const SizedBox(height: 12),
        SectionCard(
          title: 'الإقرار والنص',
          icon: Icons.gavel_rounded,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              DropdownButtonFormField<String>(
                initialValue: _rights,
                decoration: const InputDecoration(labelText: 'صفة الإذن'),
                items: const <DropdownMenuItem<String>>[
                  DropdownMenuItem(
                    value: 'self',
                    child: Text('أنا صاحب الصوت'),
                  ),
                  DropdownMenuItem(
                    value: 'explicit_authorization',
                    child: Text('لدي إذن صريح من صاحب الصوت'),
                  ),
                ],
                onChanged: (value) {
                  setState(() {
                    _rights = value ?? 'self';
                    _consent = false;
                    _statementController.clear();
                  });
                },
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _statementController,
                minLines: 2,
                maxLines: 4,
                decoration: InputDecoration(
                  labelText: 'إقرار الموافقة',
                  hintText: _rights == 'self'
                      ? 'اكتب: أنا صاحب هذا الصوت وأوافق على استنساخه.'
                      : 'اكتب وصف الإذن الصريح الذي حصلت عليه.',
                ),
                onChanged: (_) => setState(() => _consent = false),
              ),
              CheckboxListTile(
                value: _consent,
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: Text(
                  _rights == 'self'
                      ? 'أؤكد أنني صاحب الصوت وأوافق على استنساخه.'
                      : 'أؤكد أن لدي إذنًا صريحًا وقابلًا للإثبات من صاحب الصوت.',
                ),
                onChanged: _statementController.text.trim().length < 12
                    ? null
                    : (value) => setState(() => _consent = value ?? false),
              ),
              const Divider(height: 28),
              TextField(
                controller: _textController,
                minLines: 4,
                maxLines: 10,
                decoration: const InputDecoration(
                  labelText: 'النص المراد استنساخه',
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _engine,
                decoration: const InputDecoration(labelText: 'محرك الاستنساخ'),
                items: <DropdownMenuItem<String>>[
                  DropdownMenuItem(
                    value: 'elevenlabs_direct',
                    child: Text(
                      _cloudConfig.hasElevenLabs
                          ? 'ElevenLabs Pro — مباشر من الهاتف'
                          : 'ElevenLabs Pro — يحتاج مفتاحًا',
                    ),
                  ),
                  if (hasServer)
                    const DropdownMenuItem(
                      value: 'xtts',
                      child: Text('XTTS Pro على الخادم'),
                    ),
                  if (hasServer)
                    const DropdownMenuItem(
                      value: 'coqui',
                      child: Text('Coqui TTS على الخادم'),
                    ),
                  if (hasServer)
                    const DropdownMenuItem(
                      value: 'auto',
                      child: Text('اختيار خادم تلقائي'),
                    ),
                ],
                onChanged: (value) =>
                    setState(() => _engine = value ?? 'elevenlabs_direct'),
              ),
              if (_engine == 'elevenlabs_direct') ...<Widget>[
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue:
                      _selectedElevenVoice == '__new__' ||
                          _cloudVoices.any(
                            (voice) => voice.id == _selectedElevenVoice,
                          )
                      ? _selectedElevenVoice
                      : '__new__',
                  isExpanded: true,
                  decoration: const InputDecoration(
                    labelText: 'إنشاء صوت أو استخدام صوت محفوظ',
                  ),
                  items: <DropdownMenuItem<String>>[
                    const DropdownMenuItem(
                      value: '__new__',
                      child: Text('استنساخ صوت جديد من التسجيل المحدد'),
                    ),
                    ..._cloudVoices.map(
                      (voice) => DropdownMenuItem<String>(
                        value: voice.id,
                        child: Text(
                          '${voice.name} — محفوظ في ElevenLabs',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                  ],
                  onChanged: (value) =>
                      setState(() => _selectedElevenVoice = value ?? '__new__'),
                ),
                if (_selectedElevenVoice == '__new__') ...<Widget>[
                  const SizedBox(height: 12),
                  TextField(
                    controller: _voiceNameController,
                    decoration: const InputDecoration(
                      labelText: 'اسم الصوت المستنسخ',
                    ),
                  ),
                  SwitchListTile(
                    value: _removeBackgroundNoise,
                    contentPadding: EdgeInsets.zero,
                    title: const Text('تنقية ضوضاء التسجيل قبل الاستنساخ'),
                    onChanged: (value) =>
                        setState(() => _removeBackgroundNoise = value),
                  ),
                ],
              ],
              const SizedBox(height: 12),
              Text('عدد المرشحين: $_candidates'),
              Slider(
                value: _candidates.toDouble(),
                min: 2,
                max: 5,
                divisions: 3,
                onChanged: (value) =>
                    setState(() => _candidates = value.round()),
              ),
              if (_progress != null) ...<Widget>[
                LinearProgressIndicator(value: _progress),
                const SizedBox(height: 8),
              ],
              Row(
                children: <Widget>[
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: _busy || !_consent ? null : _submit,
                      icon: _busy
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.record_voice_over_rounded),
                      label: Text(
                        _engine == 'elevenlabs_direct'
                            ? 'استنساخ مباشر وإنشاء المرشحين'
                            : 'إنشاء المرشحين عبر الخادم',
                      ),
                    ),
                  ),
                  if (_busy && _engine == 'elevenlabs_direct') ...<Widget>[
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
