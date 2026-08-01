import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:voice_ai_mobile/core/constants/app_constants.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/core/utils/arabic_text_normalizer.dart';
import 'package:voice_ai_mobile/widgets/audio_result_list.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';
import 'package:voice_ai_mobile/widgets/tracked_jobs_panel.dart';

class DocumentReaderScreen extends ConsumerStatefulWidget {
  const DocumentReaderScreen({super.key});

  @override
  ConsumerState<DocumentReaderScreen> createState() =>
      _DocumentReaderScreenState();
}

class _DocumentReaderScreenState extends ConsumerState<DocumentReaderScreen> {
  final _textController = TextEditingController();
  final _voiceController = TextEditingController(text: 'default');
  String? _path;
  String? _extractedText;
  String _engine = 'local';
  double _speed = 1;
  bool _normalize = true;
  bool _busy = false;
  String? _jobId;
  Map<String, dynamic>? _result;

  @override
  void dispose() {
    _textController.dispose();
    _voiceController.dispose();
    super.dispose();
  }

  Future<void> _pickDocument() async {
    try {
      final path = await ref
          .read(documentPickerProvider)
          .pick(extensions: AppConstants.supportedDocumentExtensions.toList());
      if (path == null) return;
      setState(() {
        _path = path;
        _extractedText = null;
        _busy = true;
      });
      final extracted = await ref
          .read(localDocumentServiceProvider)
          .extractText(path);
      if (mounted) setState(() => _extractedText = extracted);
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _read() async {
    if (_path == null && _textController.text.trim().isEmpty) {
      showArabicError(context, 'اكتب نصًا أو اختر مستند PDF أو DOCX أو TXT.');
      return;
    }
    setState(() {
      _busy = true;
      _result = null;
      _jobId = null;
    });
    try {
      if (_engine == 'local') {
        var text = _path == null
            ? _textController.text.trim()
            : (_extractedText ??
                  await ref
                      .read(localDocumentServiceProvider)
                      .extractText(_path!));
        if (_normalize) text = const ArabicTextNormalizer().normalize(text);
        final output = await ref
            .read(localTtsServiceProvider)
            .synthesizeToFile(text, speed: _speed);
        if (mounted) {
          setState(
            () => _result = <String, dynamic>{
              'local_path': output,
              'name': p.basename(output),
              'engine': 'android-local-document',
            },
          );
        }
        return;
      }
      if (ref.read(appControllerProvider).session == null) {
        throw const AppException(
          'المحرك المختار يحتاج خادمًا اختياريًا. اختر «محرك الهاتف» للقراءة دون ربط.',
        );
      }
      final headers = await ref.read(providerHeadersProvider.future);
      final job = await ref
          .read(apiServiceProvider)
          .readDocument(
            path: _path,
            text: _path == null ? _textController.text.trim() : null,
            engine: _engine,
            voice: _voiceController.text.trim().isEmpty
                ? 'default'
                : _voiceController.text.trim(),
            speed: _speed,
            normalizeNumbers: _normalize,
            providerHeaders: headers,
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
    final localSelected = _engine == 'local';
    final hasServer = ref.watch(
      appControllerProvider.select((state) => state.session != null),
    );
    return ResponsivePage(
      children: <Widget>[
        Card(
          color: Theme.of(context).colorScheme.primaryContainer,
          child: ListTile(
            leading: const Icon(Icons.phone_android_rounded),
            title: const Text('قارئ محلي كامل'),
            subtitle: const Text(
              'يستخرج نص TXT وDOCX وPDF ويحوّله إلى صوت عربي داخل الهاتف.',
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
          title: 'قارئ النصوص والمستندات',
          icon: Icons.menu_book_rounded,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              TextField(
                controller: _textController,
                minLines: 6,
                maxLines: 14,
                enabled: _path == null,
                decoration: const InputDecoration(
                  labelText: 'النص',
                  hintText: 'الصق النص، أو اختر مستندًا من الهاتف...',
                  helperText:
                      'تُقرأ الأرقام والتواريخ والعملات بصياغة عربية طبيعية.',
                ),
              ),
              const SizedBox(height: 12),
              if (_path != null)
                Card.filled(
                  child: ListTile(
                    leading: const Icon(Icons.description_rounded),
                    title: Text(p.basename(_path!)),
                    subtitle: Text(
                      _extractedText == null
                          ? 'جارٍ استخراج النص محليًا...'
                          : '${_extractedText!.length} حرف جاهز للقراءة',
                    ),
                    trailing: IconButton(
                      onPressed: () => setState(() {
                        _path = null;
                        _extractedText = null;
                      }),
                      icon: const Icon(Icons.close_rounded),
                    ),
                  ),
                ),
              OutlinedButton.icon(
                onPressed: _busy ? null : _pickDocument,
                icon: const Icon(Icons.upload_file_rounded),
                label: const Text('اختيار PDF أو DOCX أو TXT'),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: <Widget>[
                  SizedBox(
                    width: 260,
                    child: DropdownButtonFormField<String>(
                      initialValue: _engine,
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
                      onChanged: (value) =>
                          setState(() => _engine = value ?? 'local'),
                    ),
                  ),
                  if (!localSelected)
                    SizedBox(
                      width: 260,
                      child: TextField(
                        controller: _voiceController,
                        decoration: const InputDecoration(labelText: 'الصوت'),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              Text('سرعة القراءة: ${_speed.toStringAsFixed(1)}×'),
              Slider(
                value: _speed,
                min: 0.5,
                max: 2,
                divisions: 15,
                onChanged: (value) => setState(() => _speed = value),
              ),
              SwitchListTile(
                value: _normalize,
                contentPadding: EdgeInsets.zero,
                title: const Text('قراءة الأرقام والتواريخ والعملات بالعربية'),
                onChanged: (value) => setState(() => _normalize = value),
              ),
              FilledButton.icon(
                onPressed: _busy ? null : _read,
                icon: _busy
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.play_circle_rounded),
                label: Text(
                  localSelected
                      ? 'إنشاء الصوت على الهاتف'
                      : 'إنشاء الكتاب الصوتي من الخادم',
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
              if (_result == null && job.result != null)
                setState(() => _result = job.result);
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
