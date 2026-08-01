import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/cloud_provider_models.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/services/local_tts_service.dart';
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
  LocalTtsStatus? _localStatus;
  CloudProviderStatus? _geminiStatus;
  CloudProviderStatus? _elevenLabsStatus;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_load);
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final localStatus = await ref.read(localTtsServiceProvider).status();
      final config = await ref.read(cloudProviderConfigProvider.future);
      CloudProviderStatus? geminiStatus;
      CloudProviderStatus? elevenLabsStatus;
      try {
        geminiStatus = await ref
            .read(cloudProviderServiceProvider)
            .checkGemini(
              apiKey: config.geminiApiKey,
              model: config.geminiModel,
            );
      } on Object catch (error) {
        geminiStatus = CloudProviderStatus(
          provider: 'gemini',
          configured: config.hasGemini,
          available: false,
          message: error.toString(),
        );
      }
      try {
        elevenLabsStatus = await ref
            .read(cloudProviderServiceProvider)
            .checkElevenLabs(apiKey: config.elevenLabsApiKey);
      } on Object catch (error) {
        elevenLabsStatus = CloudProviderStatus(
          provider: 'elevenlabs',
          configured: config.hasElevenLabs,
          available: false,
          message: error.toString(),
        );
      }
      var engines = const <EngineInfo>[];
      if (ref.read(appControllerProvider).session != null) {
        engines = await ref.read(apiServiceProvider).engines();
      }
      if (mounted) {
        setState(() {
          _localStatus = localStatus;
          _geminiStatus = geminiStatus;
          _elevenLabsStatus = elevenLabsStatus;
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

  Widget _cloudEngineCard({
    required String name,
    required String tools,
    required CloudProviderStatus? status,
  }) {
    final ready = status?.available == true;
    final configured = status?.configured == true;
    final color = ready ? Colors.green : Colors.orange;
    return Card.filled(
      child: ListTile(
        leading: Icon(
          ready ? Icons.cloud_done_rounded : Icons.key_rounded,
          color: color,
        ),
        title: Text(name),
        subtitle: Text('${status?.message ?? 'جارٍ الفحص...'}\n$tools'),
        isThreeLine: true,
        trailing: Text(
          ready ? 'جاهز' : (configured ? 'تحقق' : 'أضف مفتاحًا'),
          style: TextStyle(color: color),
        ),
      ),
    );
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
      return RefreshIndicator(
        onRefresh: _load,
        child: ResponsivePage(
          children: <Widget>[
            SectionCard(
              title: 'محركات الهاتف المحلية',
              icon: Icons.memory_rounded,
              child: Column(
                children: <Widget>[
                  Card.filled(
                    child: ListTile(
                      leading: Icon(
                        _localStatus?.installed == true
                            ? Icons.check_circle_rounded
                            : Icons.download_for_offline_rounded,
                        color: _localStatus?.installed == true
                            ? Colors.green
                            : Colors.orange,
                      ),
                      title: const Text('محرك Android للصوت العربي'),
                      subtitle: Text(
                        _localStatus?.message ?? 'جارٍ فحص محرك الصوت...',
                      ),
                      trailing: _localStatus?.installed == true
                          ? const Text(
                              'جاهز',
                              style: TextStyle(color: Colors.green),
                            )
                          : FilledButton.tonal(
                              onPressed: () => ref
                                  .read(localTtsServiceProvider)
                                  .installVoiceData(),
                              child: const Text('تنزيل'),
                            ),
                    ),
                  ),
                  const Card.filled(
                    child: ListTile(
                      leading: Icon(
                        Icons.check_circle_rounded,
                        color: Colors.green,
                      ),
                      title: Text('FFmpeg المحلي'),
                      subtitle: Text(
                        'فك الصيغ والتحويل وتحليل الجودة والمزج الصوتي على الهاتف',
                      ),
                      trailing: Text(
                        'جاهز',
                        style: TextStyle(color: Colors.green),
                      ),
                    ),
                  ),
                  _cloudEngineCard(
                    name: 'Gemini TTS المباشر',
                    tools: 'توليد مرشحين وقراءة المستندات وأداء الشيلات',
                    status: _geminiStatus,
                  ),
                  _cloudEngineCard(
                    name: 'ElevenLabs المباشر',
                    tools: 'توليد الصوت والاستنساخ الفوري ومغير الصوت',
                    status: _elevenLabsStatus,
                  ),
                  Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: OutlinedButton.icon(
                      onPressed: _load,
                      icon: const Icon(Icons.refresh_rounded),
                      label: const Text('إعادة الفحص'),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 90),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ResponsivePage(
        children: <Widget>[
          if (_error != null)
            Card(
              color: Theme.of(context).colorScheme.errorContainer,
              child: ListTile(
                title: const Text('تعذر تحميل حالة المحركات'),
                subtitle: Text(_error!),
                trailing: IconButton(
                  onPressed: _load,
                  icon: const Icon(Icons.refresh_rounded),
                ),
              ),
            ),
          SectionCard(
            title: 'محركات الهاتف والخدمات المباشرة',
            icon: Icons.phone_android_rounded,
            child: Column(
              children: <Widget>[
                _cloudEngineCard(
                  name: 'Gemini TTS المباشر',
                  tools: 'اتصال HTTPS من الهاتف دون وسيط',
                  status: _geminiStatus,
                ),
                _cloudEngineCard(
                  name: 'ElevenLabs المباشر',
                  tools: 'توليد واستنساخ HTTPS من الهاتف دون وسيط',
                  status: _elevenLabsStatus,
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          SectionCard(
            title: 'المحركات والنماذج',
            icon: Icons.memory_rounded,
            child: Column(
              children: _engines.map((engine) {
                final color = engine.downloading
                    ? Colors.orange
                    : (engine.ready ? Colors.green : Colors.redAccent);
                final status = engine.downloading
                    ? 'النموذج قيد التنزيل'
                    : (engine.ready ? 'جاهز' : 'غير جاهز');
                return Card.filled(
                  child: Padding(
                    padding: const EdgeInsets.all(8),
                    child: ListTile(
                      leading: CircleAvatar(
                        backgroundColor: color.withValues(alpha: 0.15),
                        child: Icon(
                          engine.external
                              ? Icons.cloud_rounded
                              : Icons.memory_rounded,
                          color: color,
                        ),
                      ),
                      title: Text(
                        engine.label,
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      subtitle: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            '$status${engine.external ? ' • خدمة خارجية' : ''}',
                            style: TextStyle(color: color),
                          ),
                          if (engine.models.isNotEmpty)
                            Text('النماذج: ${engine.models.join('، ')}'),
                          if (engine.error != null)
                            Text(
                              engine.error!,
                              style: TextStyle(
                                color: Theme.of(context).colorScheme.error,
                              ),
                            ),
                        ],
                      ),
                      trailing: !engine.external && !engine.ready
                          ? FilledButton.tonal(
                              onPressed: engine.downloading
                                  ? null
                                  : () => _prepare(engine),
                              child: Text(
                                engine.downloading ? 'جارٍ التنزيل' : 'تجهيز',
                              ),
                            )
                          : const Icon(
                              Icons.check_circle_rounded,
                              color: Colors.green,
                            ),
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
