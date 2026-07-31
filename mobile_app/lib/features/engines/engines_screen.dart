import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';
import 'package:voice_ai_mobile/widgets/tracked_jobs_panel.dart';

class EnginesScreen extends ConsumerStatefulWidget {
  const EnginesScreen({super.key});

  @override
  ConsumerState<EnginesScreen> createState() => _EnginesScreenState();
}

class _EnginesScreenState extends ConsumerState<EnginesScreen> {
  List<EngineInfo> _engines = const <EngineInfo>[];
  bool _loading = true;
  String? _error;
  String? _preparingJobId;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_load);
  }

  Future<void> _load() async {
    if (ref.read(appControllerProvider).session == null) {
      setState(() => _loading = false);
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final engines = await ref.read(apiServiceProvider).engines();
      if (mounted) {
        setState(() {
          _engines = engines;
          _loading = false;
        });
      }
    } on Object catch (error) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = error.toString();
        });
      }
    }
  }

  Future<void> _prepare(EngineInfo engine) async {
    try {
      final job = await ref.read(apiServiceProvider).prepareEngine(engine.name);
      await ref.read(jobControllerProvider.notifier).track(job);
      if (mounted) setState(() => _preparingJobId = job.id);
    } on Object catch (error) {
      if (mounted) showArabicError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (ref.watch(appControllerProvider).session == null) {
      return Center(
        child: FilledButton.icon(onPressed: () => context.go('/pair'), icon: const Icon(Icons.link_rounded), label: const Text('اقتران بخادم لعرض المحركات')),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ResponsivePage(
        children: <Widget>[
          if (_error != null)
            Card(
              color: Theme.of(context).colorScheme.errorContainer,
              child: ListTile(title: const Text('تعذر تحميل حالة المحركات'), subtitle: Text(_error!), trailing: IconButton(onPressed: _load, icon: const Icon(Icons.refresh_rounded))),
            ),
          SectionCard(
            title: 'المحركات والنماذج',
            icon: Icons.memory_rounded,
            child: Column(
              children: _engines.map((engine) {
                final color = engine.downloading ? Colors.orange : (engine.ready ? Colors.green : Colors.redAccent);
                final status = engine.downloading ? 'النموذج قيد التنزيل' : (engine.ready ? 'جاهز' : 'غير جاهز');
                return Card.filled(
                  child: Padding(
                    padding: const EdgeInsets.all(8),
                    child: ListTile(
                      leading: CircleAvatar(backgroundColor: color.withValues(alpha: 0.15), child: Icon(engine.external ? Icons.cloud_rounded : Icons.memory_rounded, color: color)),
                      title: Text(engine.label, style: const TextStyle(fontWeight: FontWeight.bold)),
                      subtitle: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text('$status${engine.external ? ' • خدمة خارجية' : ''}', style: TextStyle(color: color)),
                          if (engine.models.isNotEmpty) Text('النماذج: ${engine.models.join('، ')}'),
                          if (engine.error != null) Text(engine.error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                        ],
                      ),
                      trailing: !engine.external && !engine.ready
                          ? FilledButton.tonal(onPressed: engine.downloading ? null : () => _prepare(engine), child: Text(engine.downloading ? 'جارٍ التنزيل' : 'تجهيز'))
                          : const Icon(Icons.check_circle_rounded, color: Colors.green),
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
          if (_preparingJobId != null) ...<Widget>[
            const SizedBox(height: 12),
            TrackedJobsPanel(
              onlyJobId: _preparingJobId,
              onCompleted: (_) {
                _preparingJobId = null;
                _load();
              },
            ),
          ],
          const SizedBox(height: 90),
        ],
      ),
    );
  }
}
