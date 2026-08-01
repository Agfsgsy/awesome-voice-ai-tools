import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';

class AudioResultList extends ConsumerStatefulWidget {
  const AudioResultList({required this.result, super.key});

  final Map<String, dynamic> result;

  @override
  ConsumerState<AudioResultList> createState() => _AudioResultListState();
}

class _AudioResultListState extends ConsumerState<AudioResultList> {
  final Map<String, String> _localFiles = <String, String>{};
  String? _selectedId;
  double? _progress;

  List<Map<String, dynamic>> get _candidates {
    final localPath = widget.result['local_path'];
    if (localPath is String && localPath.isNotEmpty) {
      return <Map<String, dynamic>>[
        <String, dynamic>{
          'candidate_id': 'local',
          'local_path': localPath,
          'name': widget.result['name'] as String? ?? p.basename(localPath),
        },
      ];
    }
    final raw = widget.result['candidates'];
    if (raw is List<dynamic>) {
      return raw.whereType<Map<String, dynamic>>().toList();
    }
    final fileId = widget.result['file_id'];
    if (fileId is String) {
      return <Map<String, dynamic>>[
        <String, dynamic>{
          'candidate_id': 'result',
          'file_id': fileId,
          'name': widget.result['name'] as String? ?? 'voice_ai_result.wav',
        },
      ];
    }
    return const <Map<String, dynamic>>[];
  }

  Future<String> _ensureLocal(Map<String, dynamic> candidate) async {
    final localPath = candidate['local_path'];
    if (localPath is String) {
      if (await File(localPath).exists() &&
          await File(localPath).length() > 44) {
        return localPath;
      }
      throw const AppException('الملف الناتج غير صالح أو لم يعد موجودًا.');
    }
    final id = candidate['file_id'] as String;
    final cached = _localFiles[id];
    if (cached != null && await File(cached).exists()) return cached;
    final directory = await getTemporaryDirectory();
    final name = p.basename(
      candidate['name'] as String? ??
          'voice_ai_${DateTime.now().millisecondsSinceEpoch}.wav',
    );
    final destination = p.join(directory.path, name);
    final path = await ref
        .read(apiServiceProvider)
        .downloadFile(
          id,
          destination,
          onProgress: (received, total) {
            if (mounted && total > 0) {
              setState(() => _progress = received / total);
            }
          },
        );
    if (mounted) setState(() => _progress = null);
    _localFiles[id] = path;
    return path;
  }

  Future<void> _play(Map<String, dynamic> candidate) async {
    try {
      await ref
          .read(playerServiceProvider)
          .playFile(await _ensureLocal(candidate));
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    }
  }

  Future<void> _save(Map<String, dynamic> candidate) async {
    final destination = await ref
        .read(documentPickerProvider)
        .chooseSavePath(
          p.basename(candidate['name'] as String? ?? 'voice_ai_result.wav'),
        );
    if (destination == null) return;
    try {
      final localPath = candidate['local_path'];
      if (localPath is String) {
        if (!p.equals(localPath, destination)) {
          await File(localPath).copy(destination);
        }
      } else {
        await ref
            .read(apiServiceProvider)
            .downloadFile(
              candidate['file_id'] as String,
              destination,
              onProgress: (received, total) {
                if (mounted && total > 0) {
                  setState(() => _progress = received / total);
                }
              },
            );
      }
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('تم حفظ الملف بنجاح.')));
      }
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      if (mounted) setState(() => _progress = null);
    }
  }

  Future<void> _share(Map<String, dynamic> candidate) async {
    try {
      final path = await _ensureLocal(candidate);
      if (!mounted) return;
      final box = context.findRenderObject() as RenderBox?;
      await SharePlus.instance.share(
        ShareParams(
          files: <XFile>[XFile(path)],
          text: 'ملف صوتي من Voice AI Studio',
          sharePositionOrigin: box == null
              ? null
              : box.localToGlobal(Offset.zero) & box.size,
        ),
      );
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    }
  }

  Future<void> _addToProject(Map<String, dynamic> candidate) async {
    try {
      var projects = await ref.read(projectServiceProvider).list();
      if (!mounted) return;
      if (projects.isEmpty) {
        final controller = TextEditingController();
        final name = await showDialog<String>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('مشروع محلي جديد'),
            content: TextField(
              controller: controller,
              autofocus: true,
              decoration: const InputDecoration(labelText: 'اسم المشروع'),
            ),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('إلغاء'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, controller.text.trim()),
                child: const Text('إنشاء'),
              ),
            ],
          ),
        );
        controller.dispose();
        if (name == null || name.isEmpty) return;
        await ref.read(projectServiceProvider).create(name);
        projects = await ref.read(projectServiceProvider).list();
      }
      if (!mounted || projects.isEmpty) return;
      final selected = await showDialog<SavedProject>(
        context: context,
        builder: (context) => SimpleDialog(
          title: const Text('حفظ النتيجة في مشروع'),
          children: projects
              .map(
                (project) => SimpleDialogOption(
                  onPressed: () => Navigator.pop(context, project),
                  child: Text(project.name),
                ),
              )
              .toList(),
        ),
      );
      if (selected == null) return;
      final path = await _ensureLocal(candidate);
      await ref.read(projectServiceProvider).addFile(selected.id, path);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('حُفظ الملف في مشروع «${selected.name}».')),
        );
      }
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final candidates = _candidates;
    if (candidates.isEmpty) {
      return const Text('اكتملت العملية، لكن لم يُنتج ملف صوتي صالح.');
    }
    final best = widget.result['best_candidate_id'] as String?;
    _selectedId ??= best ?? candidates.first['candidate_id'] as String?;
    return SectionCard(
      title: candidates.length > 1 ? 'اختر أفضل نتيجة' : 'النتيجة الصوتية',
      icon: Icons.library_music_rounded,
      child: RadioGroup<String>(
        groupValue: _selectedId,
        onChanged: (value) => setState(() => _selectedId = value),
        child: Column(
          children: <Widget>[
            if (_progress != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: LinearProgressIndicator(value: _progress),
              ),
            ...candidates.asMap().entries.map((entry) {
              final candidate = entry.value;
              final candidateId =
                  candidate['candidate_id'] as String? ?? '${entry.key}';
              return Card.filled(
                child: Padding(
                  padding: const EdgeInsets.all(8),
                  child: Row(
                    children: <Widget>[
                      Radio<String>(value: candidateId),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              candidates.length == 1
                                  ? 'النتيجة جاهزة'
                                  : 'المرشح ${entry.key + 1}',
                              style: const TextStyle(
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            if (candidateId == best)
                              const Text(
                                'النتيجة المقترحة تلقائيًا',
                                style: TextStyle(color: Color(0xFF14B8A6)),
                              ),
                          ],
                        ),
                      ),
                      IconButton(
                        tooltip: 'تشغيل',
                        onPressed: () => _play(candidate),
                        icon: const Icon(Icons.play_circle_fill_rounded),
                      ),
                      IconButton(
                        tooltip: 'حفظ',
                        onPressed: () => _save(candidate),
                        icon: const Icon(Icons.download_rounded),
                      ),
                      IconButton(
                        tooltip: 'مشاركة',
                        onPressed: () => _share(candidate),
                        icon: const Icon(Icons.share_rounded),
                      ),
                    ],
                  ),
                ),
              );
            }),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: Wrap(
                spacing: 8,
                children: <Widget>[
                  TextButton.icon(
                    onPressed: () => ref.read(playerServiceProvider).stop(),
                    icon: const Icon(Icons.stop_circle_outlined),
                    label: const Text('إيقاف التشغيل'),
                  ),
                  TextButton.icon(
                    onPressed: () {
                      final selected = candidates.firstWhere(
                        (candidate) => candidate['candidate_id'] == _selectedId,
                        orElse: () => candidates.first,
                      );
                      _addToProject(selected);
                    },
                    icon: const Icon(Icons.create_new_folder_rounded),
                    label: const Text('حفظ في مشروع'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
