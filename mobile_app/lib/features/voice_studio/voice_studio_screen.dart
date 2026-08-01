import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
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
  List<EngineInfo> _engines = const <EngineInfo>[];
  String _engine = 'local';
  double _speed = 1;
  int _candidates = 2;
  bool _loading = false;
  String? _jobId;
  Map<String, dynamic>? _result;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_loadEngines);
  }

  @override
  void dispose() {
    _textController.dispose();
    _voiceController.dispose();
    super.dispose();
  }

  Future<void> _loadEngines() async {
    if (ref.read(appControllerProvider).session == null) return;
    try {
      final engines = await ref.read(apiServiceProvider).engines();
      if (mounted) setState(() => _engines = engines);
    } on Object {
      // تظهر حالة الاتصال العامة، ويمكن إعادة المحاولة عند تنفيذ الطلب.
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
    });
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
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final wordCount = _textController.text.trim().isEmpty
        ? 0
        : _textController.text.trim().split(RegExp(r'\s+')).length;
    final localSelected = _engine == 'local';
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
                    'محرك الهاتف هو الافتراضي ويُنشئ الملف محليًا. إذا لم تكن العربية مثبتة، نزّل بياناتها مرة واحدة من إعدادات Android.',
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
                        onChanged: (value) =>
                            setState(() => _engine = value ?? 'local'),
                      ),
                    ),
                    if (!localSelected)
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
              FilledButton.icon(
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
                      : 'توليد الصوت من الخادم',
                ),
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
