import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';
import 'package:voice_ai_mobile/widgets/tracked_jobs_panel.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  bool _loading = true;
  String? _error;
  Map<String, dynamic>? _status;
  List<EngineInfo> _engines = const <EngineInfo>[];
  List<MobileFileInfo> _files = const <MobileFileInfo>[];

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_load);
  }

  Future<void> _load() async {
    final appState = ref.read(appControllerProvider);
    if (appState.session == null) {
      setState(() {
        _loading = false;
        _error = null;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ref.read(apiServiceProvider);
      final status = await api.status();
      final results = await Future.wait<Object>(<Future<Object>>[api.engines(), api.files()]);
      if (!mounted) return;
      setState(() {
        _status = status;
        _engines = results[0] as List<EngineInfo>;
        _files = results[1] as List<MobileFileInfo>;
        _loading = false;
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final appState = ref.watch(appControllerProvider);
    if (_loading) return const Center(child: CircularProgressIndicator());
    final readyEngines = _engines.where((engine) => engine.ready).length;
    return RefreshIndicator(
      onRefresh: _load,
      child: ResponsivePage(
        children: <Widget>[
          if (_error != null)
            Card(
              color: Theme.of(context).colorScheme.errorContainer,
              child: ListTile(
                leading: const Icon(Icons.cloud_off_rounded),
                title: const Text('الخادم غير متصل'),
                subtitle: Text(_error!),
                trailing: IconButton(onPressed: _load, icon: const Icon(Icons.refresh_rounded)),
              ),
            ),
          if (appState.localMode && appState.session == null)
            Card(
              child: ListTile(
                leading: const Icon(Icons.phone_android_rounded, color: Color(0xFF14B8A6)),
                title: const Text('الوضع المحلي نشط'),
                subtitle: const Text('التسجيل والمعاينة والتحويل والتحليل المحلي متاحة. اربط خادمًا لتشغيل XTTS والمحركات الثقيلة.'),
                trailing: FilledButton(onPressed: () => context.go('/pair'), child: const Text('اقتران')),
              ),
            ),
          LayoutBuilder(
            builder: (context, constraints) {
              final width = constraints.maxWidth >= 760 ? (constraints.maxWidth - 36) / 4 : (constraints.maxWidth - 12) / 2;
              return Wrap(
                spacing: 12,
                runSpacing: 12,
                children: <Widget>[
                  _StatCard(width: width, label: 'الملفات', value: '${_files.length}', icon: Icons.audio_file_rounded),
                  _StatCard(width: width, label: 'المحركات الجاهزة', value: '$readyEngines/${_engines.length}', icon: Icons.memory_rounded),
                  _StatCard(width: width, label: 'واجهة الجوال', value: _status?['mobile_api_version'] as String? ?? 'محلي', icon: Icons.phone_android_rounded),
                  _StatCard(width: width, label: 'الحالة', value: appState.online ? 'متصل' : 'محلي', icon: appState.online ? Icons.check_circle_rounded : Icons.offline_bolt_rounded),
                ],
              );
            },
          ),
          const SizedBox(height: 12),
          SectionCard(
            title: 'وصول سريع',
            icon: Icons.bolt_rounded,
            child: Wrap(
              spacing: 10,
              runSpacing: 10,
              children: <Widget>[
                _Shortcut(label: 'تسجيل جديد', icon: Icons.mic_rounded, onTap: () => context.go('/record')),
                _Shortcut(label: 'استنساخ Pro', icon: Icons.record_voice_over_rounded, onTap: () => context.go('/clone')),
                _Shortcut(label: 'قارئ المستندات', icon: Icons.menu_book_rounded, onTap: () => context.go('/documents')),
                _Shortcut(label: 'استوديو الشيلات', icon: Icons.library_music_rounded, onTap: () => context.go('/songs')),
              ],
            ),
          ),
          const SizedBox(height: 12),
          const TrackedJobsPanel(),
          if (_files.isNotEmpty) ...<Widget>[
            const SizedBox(height: 12),
            SectionCard(
              title: 'أحدث الملفات',
              icon: Icons.history_rounded,
              child: Column(
                children: _files
                    .take(5)
                    .map((file) => ListTile(leading: Icon(file.isAudio ? Icons.audiotrack_rounded : Icons.insert_drive_file_rounded), title: Text(file.name), subtitle: Text(file.scope)))
                    .toList(),
              ),
            ),
          ],
          const SizedBox(height: 80),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({required this.width, required this.label, required this.value, required this.icon});

  final double width;
  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: width,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(icon, color: const Color(0xFF14B8A6)),
                const SizedBox(height: 12),
                Text(label, style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 4),
                Text(value, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
              ],
            ),
          ),
        ),
      );
}

class _Shortcut extends StatelessWidget {
  const _Shortcut({required this.label, required this.icon, required this.onTap});

  final String label;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => FilledButton.tonalIcon(onPressed: onTap, icon: Icon(icon), label: Text(label));
}
