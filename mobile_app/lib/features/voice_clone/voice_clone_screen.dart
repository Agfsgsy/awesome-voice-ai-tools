import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:path/path.dart' as p;
import 'package:voice_ai_mobile/core/providers/providers.dart';
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
  bool _consent = false;
  bool _busy = false;
  String _rights = 'self';
  String _engine = 'xtts';
  int _candidates = 3;
  String? _jobId;
  Map<String, dynamic>? _result;

  @override
  void dispose() {
    _textController.dispose();
    _statementController.dispose();
    super.dispose();
  }

  Future<void> _chooseReference() async {
    try {
      final path = await ref.read(documentPickerProvider).pickAny();
      if (path == null) return;
      setState(() => _busy = true);
      if (ref.read(appControllerProvider).session == null) {
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
    if (ref.read(appControllerProvider).session == null) {
      showArabicError(
        context,
        'استنساخ XTTS الكامل يحتاج نموذجًا كبيرًا لا يناسب ذاكرة الهاتف. استخدم محرك الهاتف من الاستوديو دون ربط، أو أضف خادمًا اختياريًا لاحقًا.',
      );
      return;
    }
    if (reference == null) {
      showArabicError(context, 'سجّل صوتًا مرجعيًا أو اختر ملفًا وحلله أولًا.');
      return;
    }
    if (reference.fileId.isEmpty) {
      showArabicError(
        context,
        'أعد اختيار التسجيل بعد الاتصال بالخادم لرفعه قبل تشغيل XTTS Pro.',
      );
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
    });
    try {
      final job = await ref
          .read(apiServiceProvider)
          .cloneVoice(
            referenceFileId: reference.fileId,
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
      if (mounted) setState(() => _busy = false);
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
        if (!hasServer) ...<Widget>[
          Card(
            color: Theme.of(context).colorScheme.primaryContainer,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  const Text(
                    'الاستنساخ العصبي Pro اختياري',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'يمكن للهاتف تسجيل الصوت وتحليله محليًا، لكن نموذج XTTS الكامل أكبر من موارد أغلب الهواتف. توليد الصوت العربي العادي يعمل محليًا الآن دون أي ربط.',
                  ),
                  const SizedBox(height: 10),
                  FilledButton.icon(
                    onPressed: () => context.go('/studio'),
                    icon: const Icon(Icons.phone_android_rounded),
                    label: const Text('فتح محرك الهاتف المحلي'),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
        ],
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
                items: const <DropdownMenuItem<String>>[
                  DropdownMenuItem(value: 'xtts', child: Text('XTTS Pro')),
                  DropdownMenuItem(value: 'coqui', child: Text('Coqui TTS')),
                  DropdownMenuItem(value: 'auto', child: Text('اختيار تلقائي')),
                ],
                onChanged: (value) => setState(() => _engine = value ?? 'xtts'),
              ),
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
              if (hasServer)
                FilledButton.icon(
                  onPressed: _busy || !_consent ? null : _submit,
                  icon: _busy
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.record_voice_over_rounded),
                  label: const Text('إنشاء المرشحين واختيار الأفضل'),
                )
              else
                FilledButton.icon(
                  onPressed: () => context.go('/studio'),
                  icon: const Icon(Icons.offline_bolt_rounded),
                  label: const Text('إنشاء صوت عربي محلي بدلًا من ذلك'),
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
