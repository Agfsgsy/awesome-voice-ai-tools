import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/core/utils/formatters.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';

class FilesScreen extends ConsumerStatefulWidget {
  const FilesScreen({super.key});

  @override
  ConsumerState<FilesScreen> createState() => _FilesScreenState();
}

class _FilesScreenState extends ConsumerState<FilesScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  List<MobileFileInfo> _files = const <MobileFileInfo>[];
  List<SavedProject> _projects = const <SavedProject>[];
  bool _loading = true;
  String? _busyFileId;
  double? _progress;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    Future<void>.microtask(_load);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final projects = await ref.read(projectServiceProvider).list();
      final files = ref.read(appControllerProvider).session == null ? const <MobileFileInfo>[] : await ref.read(apiServiceProvider).files();
      if (mounted) {
        setState(() {
          _projects = projects;
          _files = files;
          _loading = false;
        });
      }
    } on Object catch (error) {
      if (mounted) {
        setState(() => _loading = false);
        showArabicError(context, error);
      }
    }
  }

  Future<String> _downloadTemporary(MobileFileInfo file) async {
    final directory = await getTemporaryDirectory();
    final target = p.join(directory.path, 'mobile_${file.id.hashCode}_${p.basename(file.name)}');
    return ref.read(apiServiceProvider).downloadFile(
          file.id,
          target,
          onProgress: (received, total) {
            if (mounted && total > 0) setState(() => _progress = received / total);
          },
        );
  }

  Future<void> _withFile(MobileFileInfo file, Future<void> Function() action) async {
    setState(() {
      _busyFileId = file.id;
      _progress = 0;
    });
    try {
      await action();
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    } finally {
      if (mounted) {
        setState(() {
          _busyFileId = null;
          _progress = null;
        });
      }
    }
  }

  Future<void> _play(MobileFileInfo file) => _withFile(file, () async {
        final local = await _downloadTemporary(file);
        await ref.read(playerServiceProvider).playFile(local);
      });

  Future<void> _save(MobileFileInfo file) => _withFile(file, () async {
        final destination = await ref.read(documentPickerProvider).chooseSavePath(file.name);
        if (destination == null) return;
        await ref.read(apiServiceProvider).downloadFile(
          file.id,
          destination,
          onProgress: (received, total) {
            if (mounted && total > 0) setState(() => _progress = received / total);
          },
        );
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('تم تنزيل الملف وحفظه.')));
      });

  Future<void> _share(MobileFileInfo file) => _withFile(file, () async {
        final local = await _downloadTemporary(file);
        if (!mounted) return;
        final box = context.findRenderObject() as RenderBox?;
        await SharePlus.instance.share(
          ShareParams(
            files: <XFile>[XFile(local)],
            text: 'ملف من Voice AI Studio',
            sharePositionOrigin: box == null ? null : box.localToGlobal(Offset.zero) & box.size,
          ),
        );
      });

  Future<void> _deleteServerFile(MobileFileInfo file) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('حذف الملف'),
        content: Text('هل تريد حذف ${file.name} من الخادم؟ لا يمكن التراجع عن ذلك.'),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('إلغاء')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('حذف')),
        ],
      ),
    );
    if (confirmed != true) return;
    await _withFile(file, () => ref.read(apiServiceProvider).deleteFile(file.id));
    await _load();
  }

  Future<void> _createProject() async {
    final controller = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('مشروع جديد'),
        content: TextField(controller: controller, autofocus: true, decoration: const InputDecoration(labelText: 'اسم المشروع')),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('إلغاء')),
          FilledButton(onPressed: () => Navigator.pop(context, controller.text.trim()), child: const Text('إنشاء')),
        ],
      ),
    );
    controller.dispose();
    if (name == null || name.isEmpty) return;
    await ref.read(projectServiceProvider).create(name);
    await _load();
  }

  Future<void> _addToProject(MobileFileInfo file) async {
    if (_projects.isEmpty) {
      await _createProject();
      if (_projects.isEmpty) return;
    }
    if (!mounted) return;
    final project = await showDialog<SavedProject>(
      context: context,
      builder: (context) => SimpleDialog(
        title: const Text('حفظ في مشروع'),
        children: _projects
            .map((project) => SimpleDialogOption(onPressed: () => Navigator.pop(context, project), child: Text(project.name)))
            .toList(),
      ),
    );
    if (project == null) return;
    await _withFile(file, () async {
      final local = await _downloadTemporary(file);
      await ref.read(projectServiceProvider).addFile(project.id, local);
    });
    await _load();
  }

  Future<void> _deleteProject(SavedProject project) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('حذف المشروع'),
        content: Text('سيُحذف مشروع «${project.name}» ونسخه المحلية المحفوظة.'),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('إلغاء')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('حذف')),
        ],
      ),
    );
    if (confirmed == true) {
      await ref.read(projectServiceProvider).delete(project.id);
      await _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Column(
      children: <Widget>[
        TabBar(controller: _tabs, tabs: const <Tab>[Tab(icon: Icon(Icons.cloud_rounded), text: 'ملفات الخادم'), Tab(icon: Icon(Icons.folder_copy_rounded), text: 'المشاريع المحلية')]),
        if (_progress != null) LinearProgressIndicator(value: _progress),
        Expanded(
          child: TabBarView(
            controller: _tabs,
            children: <Widget>[
              RefreshIndicator(
                onRefresh: _load,
                child: _files.isEmpty
                    ? ListView(children: const <Widget>[SizedBox(height: 160), Icon(Icons.folder_off_rounded, size: 64), Center(child: Text('لا توجد ملفات على الخادم أو أن الوضع المحلي نشط.'))])
                    : ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: _files.length,
                        itemBuilder: (context, index) {
                          final file = _files[index];
                          return Card(
                            child: ListTile(
                              leading: CircleAvatar(child: Icon(file.isAudio ? Icons.audiotrack_rounded : Icons.insert_drive_file_rounded)),
                              title: Text(file.name),
                              subtitle: Text('${formatBytes(file.size)} • ${formatDate(file.modifiedAt)}'),
                              trailing: _busyFileId == file.id
                                  ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))
                                  : PopupMenuButton<String>(
                                      onSelected: (action) => switch (action) {
                                        'play' => _play(file),
                                        'save' => _save(file),
                                        'share' => _share(file),
                                        'project' => _addToProject(file),
                                        'delete' => _deleteServerFile(file),
                                        _ => null,
                                      },
                                      itemBuilder: (context) => <PopupMenuEntry<String>>[
                                        if (file.isAudio) const PopupMenuItem(value: 'play', child: Text('تشغيل')),
                                        const PopupMenuItem(value: 'save', child: Text('تنزيل وحفظ')),
                                        const PopupMenuItem(value: 'share', child: Text('مشاركة')),
                                        const PopupMenuItem(value: 'project', child: Text('إضافة إلى مشروع')),
                                        const PopupMenuDivider(),
                                        const PopupMenuItem(value: 'delete', child: Text('حذف')),
                                      ],
                                    ),
                            ),
                          );
                        },
                      ),
              ),
              RefreshIndicator(
                onRefresh: _load,
                child: ListView(
                  padding: const EdgeInsets.all(12),
                  children: <Widget>[
                    FilledButton.tonalIcon(onPressed: _createProject, icon: const Icon(Icons.create_new_folder_rounded), label: const Text('إنشاء مشروع جديد')),
                    const SizedBox(height: 12),
                    if (_projects.isEmpty) const Padding(padding: EdgeInsets.all(48), child: Center(child: Text('لا توجد مشاريع محلية بعد.'))),
                    ..._projects.map(
                      (project) => Card(
                        child: ExpansionTile(
                          leading: const Icon(Icons.folder_rounded, color: Color(0xFF14B8A6)),
                          title: Text(project.name),
                          subtitle: Text('${project.filePaths.length} ملف • ${formatDate(project.createdAt)}'),
                          trailing: IconButton(onPressed: () => _deleteProject(project), icon: const Icon(Icons.delete_outline_rounded)),
                          children: project.filePaths
                              .map(
                                (path) => ListTile(
                                  leading: const Icon(Icons.audiotrack_rounded),
                                  title: Text(p.basename(path)),
                                  onTap: () => ref.read(playerServiceProvider).playFile(path),
                                  trailing: IconButton(
                                    onPressed: () {
                                      final box = context.findRenderObject() as RenderBox?;
                                      SharePlus.instance.share(
                                        ShareParams(
                                          files: <XFile>[XFile(path)],
                                          sharePositionOrigin: box == null ? null : box.localToGlobal(Offset.zero) & box.size,
                                        ),
                                      );
                                    },
                                    icon: const Icon(Icons.share_rounded),
                                  ),
                                ),
                              )
                              .toList(),
                        ),
                      ),
                    ),
                    const SizedBox(height: 90),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
