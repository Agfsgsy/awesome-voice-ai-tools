import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:path/path.dart' as p;
import 'package:voice_ai_mobile/core/providers/providers.dart';
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
  String _engine = 'auto';
  int _candidates = 3;
  double _tempo = 1;
  double _pitch = 0;
  double _reverb = 0.25;
  String? _instrumentalPath;
  String? _instrumentalFileId;
  bool _busy = false;
  double? _uploadProgress;
  String? _jobId;
  Map<String, dynamic>? _result;

  @override
  void dispose() {
    _titleController.dispose();
    _lyricsController.dispose();
    _voiceController.dispose();
    super.dispose();
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
    final id = await ref.read(apiServiceProvider).uploadResumable(
          _instrumentalPath!,
          onProgress: (sent, total) {
            if (mounted) setState(() => _uploadProgress = total > 0 ? sent / total : null);
          },
        );
    _instrumentalFileId = id;
    return id;
  }

  Future<void> _generate() async {
    if (ref.read(appControllerProvider).session == null) {
      context.go('/pair');
      return;
    }
    if (_titleController.text.trim().isEmpty || _lyricsController.text.trim().isEmpty) {
      showArabicError(context, 'أدخل عنوان المشروع وكلمات الشيلة أو الأغنية.');
      return;
    }
    setState(() {
      _busy = true;
      _result = null;
    });
    try {
      final headers = await ref.read(providerHeadersProvider.future);
      final instrumentalId = await _uploadInstrumental();
      final job = await ref.read(apiServiceProvider).generateSong(
            title: _titleController.text.trim(),
            lyrics: _lyricsController.text.trim(),
            style: _style,
            engine: _engine,
            voice: _voiceController.text.trim().isEmpty ? 'default' : _voiceController.text.trim(),
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
      if (mounted) {
        setState(() {
          _busy = false;
          _uploadProgress = null;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => ResponsivePage(
        children: <Widget>[
          SectionCard(
            title: 'استوديو الشيلات والأغاني',
            icon: Icons.library_music_rounded,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                TextField(controller: _titleController, decoration: const InputDecoration(labelText: 'اسم المشروع')),
                const SizedBox(height: 12),
                TextField(controller: _lyricsController, minLines: 8, maxLines: 18, decoration: const InputDecoration(labelText: 'الكلمات', hintText: 'اكتب الأبيات أو كلمات الأغنية هنا...')),
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
                        items: const <String>['شيلة عربية', 'شيلة حماسية', 'شيلة هادئة', 'أغنية عربية', 'إنشاد دون موسيقى']
                            .map((value) => DropdownMenuItem(value: value, child: Text(value)))
                            .toList(),
                        onChanged: (value) => setState(() => _style = value ?? 'شيلة عربية'),
                      ),
                    ),
                    SizedBox(
                      width: 270,
                      child: DropdownButtonFormField<String>(
                        initialValue: _engine,
                        decoration: const InputDecoration(labelText: 'المحرك'),
                        items: const <DropdownMenuItem<String>>[
                          DropdownMenuItem(value: 'auto', child: Text('اختيار تلقائي')),
                          DropdownMenuItem(value: 'xtts', child: Text('XTTS')),
                          DropdownMenuItem(value: 'elevenlabs', child: Text('ElevenLabs')),
                          DropdownMenuItem(value: 'gemini', child: Text('Gemini TTS')),
                        ],
                        onChanged: (value) => setState(() => _engine = value ?? 'auto'),
                      ),
                    ),
                    SizedBox(width: 270, child: TextField(controller: _voiceController, decoration: const InputDecoration(labelText: 'الصوت'))),
                  ],
                ),
                const SizedBox(height: 12),
                Card.filled(
                  child: ListTile(
                    leading: const Icon(Icons.piano_rounded),
                    title: Text(_instrumentalPath == null ? 'مسار موسيقي اختياري' : p.basename(_instrumentalPath!)),
                    subtitle: const Text('يمكن تركه فارغًا للإنشاد دون موسيقى'),
                    trailing: IconButton(onPressed: _pickInstrumental, icon: const Icon(Icons.folder_open_rounded)),
                  ),
                ),
                if (_uploadProgress != null) LinearProgressIndicator(value: _uploadProgress),
                const SizedBox(height: 12),
                Text('الإيقاع: ${_tempo.toStringAsFixed(2)}×'),
                Slider(value: _tempo, min: 0.5, max: 2, divisions: 30, onChanged: (value) => setState(() => _tempo = value)),
                Text('طبقة الصوت: ${_pitch.toStringAsFixed(1)} نصف درجة'),
                Slider(value: _pitch, min: -6, max: 6, divisions: 24, onChanged: (value) => setState(() => _pitch = value)),
                Text('الصدى: ${(_reverb * 100).round()}٪'),
                Slider(value: _reverb, max: 1, divisions: 20, onChanged: (value) => setState(() => _reverb = value)),
                Text('عدد المرشحين: $_candidates'),
                Slider(value: _candidates.toDouble(), min: 1, max: 5, divisions: 4, onChanged: (value) => setState(() => _candidates = value.round())),
                FilledButton.icon(
                  onPressed: _busy ? null : _generate,
                  icon: _busy ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.auto_awesome_rounded),
                  label: const Text('إنشاء المشروع الصوتي'),
                ),
              ],
            ),
          ),
          if (_jobId != null) ...<Widget>[
            const SizedBox(height: 12),
            TrackedJobsPanel(
              onlyJobId: _jobId,
              onCompleted: (job) {
                if (_result == null && job.result != null) setState(() => _result = job.result);
              },
            ),
          ],
          if (_result != null) ...<Widget>[const SizedBox(height: 12), AudioResultList(result: _result!)],
          const SizedBox(height: 90),
        ],
      );
}
