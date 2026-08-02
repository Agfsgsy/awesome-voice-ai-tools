import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/cloud_provider_models.dart';
import 'package:voice_ai_mobile/services/cloud_provider_service.dart';
import 'package:voice_ai_mobile/services/local_tts_service.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final _geminiKey = TextEditingController();
  final _geminiModel = TextEditingController(
    text: 'gemini-3.1-flash-tts-preview',
  );
  final _geminiTextModel = TextEditingController(text: 'gemini-3.6-flash');
  final _elevenLabsKey = TextEditingController();
  final _elevenLabsModel = TextEditingController(
    text: 'eleven_multilingual_v2',
  );
  final _elevenLabsStsModel = TextEditingController(
    text: 'eleven_multilingual_sts_v2',
  );
  bool _loading = true;
  bool _saving = false;
  bool _showSecrets = false;
  bool _checkingVoice = false;
  bool _testingGemini = false;
  bool _testingElevenLabs = false;
  String _geminiVoice = 'Kore';
  LocalTtsStatus? _voiceStatus;
  CloudProviderStatus? _geminiStatus;
  CloudProviderStatus? _elevenLabsStatus;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_load);
  }

  @override
  void dispose() {
    _geminiKey.dispose();
    _geminiModel.dispose();
    _geminiTextModel.dispose();
    _elevenLabsKey.dispose();
    _elevenLabsModel.dispose();
    _elevenLabsStsModel.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final storage = ref.read(secureStorageProvider);
    _geminiKey.text = await storage.readSecret('gemini_api_key') ?? '';
    _geminiModel.text =
        await storage.readSecret('gemini_model') ?? _geminiModel.text;
    _geminiVoice = await storage.readSecret('gemini_voice') ?? 'Kore';
    _geminiTextModel.text =
        await storage.readSecret('gemini_text_model') ?? _geminiTextModel.text;
    _elevenLabsKey.text = await storage.readSecret('elevenlabs_api_key') ?? '';
    _elevenLabsModel.text =
        await storage.readSecret('elevenlabs_model') ?? _elevenLabsModel.text;
    _elevenLabsStsModel.text =
        await storage.readSecret('elevenlabs_sts_model') ??
            _elevenLabsStsModel.text;
    if (!mounted) return;
    setState(() => _loading = false);
    await _checkLocalVoice();
  }

  Future<void> _checkLocalVoice() async {
    if (mounted) setState(() => _checkingVoice = true);
    final status = await ref.read(localTtsServiceProvider).status();
    if (mounted) {
      setState(() {
        _voiceStatus = status;
        _checkingVoice = false;
      });
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    await _persistCloudSettings();
    if (mounted) {
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('حُفظت الإعدادات مشفرة داخل مخزن النظام الآمن.'),
        ),
      );
    }
  }

  Future<void> _persistCloudSettings() async {
    final storage = ref.read(secureStorageProvider);
    await storage.writeSecret('gemini_api_key', _geminiKey.text.trim());
    await storage.writeSecret('gemini_model', _geminiModel.text.trim());
    await storage.writeSecret('gemini_voice', _geminiVoice);
    await storage.writeSecret(
      'gemini_text_model',
      _geminiTextModel.text.trim(),
    );
    await storage.writeSecret(
      'elevenlabs_api_key',
      _elevenLabsKey.text.trim(),
    );
    await storage.writeSecret(
      'elevenlabs_model',
      _elevenLabsModel.text.trim(),
    );
    await storage.writeSecret(
      'elevenlabs_sts_model',
      _elevenLabsStsModel.text.trim(),
    );
    ref.invalidate(providerHeadersProvider);
    ref.invalidate(cloudProviderConfigProvider);
  }

  Future<void> _testGemini() async {
    setState(() {
      _testingGemini = true;
      _geminiStatus = null;
    });
    try {
      final status = await ref.read(cloudProviderServiceProvider).checkGemini(
            apiKey: _geminiKey.text.trim(),
            model: _geminiModel.text.trim(),
            textModel: _geminiTextModel.text.trim(),
            voice: _geminiVoice,
            verifyGeneration: true,
          );
      await _persistCloudSettings();
      if (mounted) setState(() => _geminiStatus = status);
    } on Object catch (error) {
      if (mounted) {
        setState(() {
          _geminiStatus = CloudProviderStatus(
            provider: 'gemini',
            configured: _geminiKey.text.trim().isNotEmpty,
            available: false,
            message: error.toString(),
          );
        });
        showArabicError(context, error);
      }
    } finally {
      if (mounted) setState(() => _testingGemini = false);
    }
  }

  Future<void> _testElevenLabs() async {
    setState(() {
      _testingElevenLabs = true;
      _elevenLabsStatus = null;
    });
    try {
      final status = await ref
          .read(cloudProviderServiceProvider)
          .checkElevenLabs(
            apiKey: _elevenLabsKey.text.trim(),
            ttsModel: _elevenLabsModel.text.trim(),
            stsModel: _elevenLabsStsModel.text.trim(),
            verifyGeneration: true,
          );
      await _persistCloudSettings();
      if (mounted) setState(() => _elevenLabsStatus = status);
    } on Object catch (error) {
      if (mounted) {
        setState(() {
          _elevenLabsStatus = CloudProviderStatus(
            provider: 'elevenlabs',
            configured: _elevenLabsKey.text.trim().isNotEmpty,
            available: false,
            message: error.toString(),
          );
        });
        showArabicError(context, error);
      }
    } finally {
      if (mounted) setState(() => _testingElevenLabs = false);
    }
  }

  Future<void> _disconnect() async {
    await ref.read(appControllerProvider.notifier).disconnect();
    if (mounted) context.go('/dashboard');
  }

  Widget _providerStatusTile(CloudProviderStatus status) {
    final ready = status.available;
    final color = ready ? Colors.green : Theme.of(context).colorScheme.error;
    return Card.filled(
      color: color.withValues(alpha: 0.10),
      child: ListTile(
        leading: Icon(
          ready ? Icons.verified_rounded : Icons.error_rounded,
          color: color,
        ),
        title: Text(
          status.verifiedByGeneration && ready
              ? 'متصل فعليًا 100%'
              : (ready ? 'متصل' : 'فشل الاتصال'),
          style: TextStyle(color: color, fontWeight: FontWeight.bold),
        ),
        subtitle: Text(
          <String>[
            status.message,
            ...status.capabilities.map((item) => '✓ $item'),
          ].join('\n'),
        ),
        isThreeLine: status.capabilities.isNotEmpty,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    final appState = ref.watch(appControllerProvider);
    return ResponsivePage(
      children: <Widget>[
        SectionCard(
          title: 'الخادم الاختياري للمحركات الثقيلة',
          icon: Icons.dns_rounded,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(
                  appState.online
                      ? Icons.cloud_done_rounded
                      : Icons.cloud_off_rounded,
                  color: appState.online ? Colors.green : Colors.orange,
                ),
                title: Text(
                  appState.online
                      ? 'الخادم متصل'
                      : (appState.session == null
                          ? 'لا حاجة إلى خادم'
                          : 'الخادم غير متصل'),
                ),
                subtitle: Text(
                  appState.session?.serverUrl ??
                      'التطبيق يعمل محليًا على الهاتف',
                  textDirection: appState.session == null
                      ? TextDirection.rtl
                      : TextDirection.ltr,
                ),
                trailing: appState.session == null
                    ? const Icon(
                        Icons.offline_bolt_rounded,
                        color: Color(0xFF14B8A6),
                      )
                    : IconButton(
                        tooltip: 'اختبار الاتصال',
                        onPressed: () => ref
                            .read(appControllerProvider.notifier)
                            .checkConnection(),
                        icon: const Icon(Icons.refresh_rounded),
                      ),
              ),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: <Widget>[
                  FilledButton.tonalIcon(
                    onPressed: () => context.go('/pair'),
                    icon: const Icon(Icons.qr_code_scanner_rounded),
                    label: Text(
                      appState.session == null
                          ? 'اقتران بخادم'
                          : 'إعادة الاقتران بخادم آخر',
                    ),
                  ),
                  if (appState.session != null)
                    OutlinedButton.icon(
                      onPressed: _disconnect,
                      icon: const Icon(Icons.link_off_rounded),
                      label: const Text('فصل هذا الهاتف'),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              const Text(
                'اختياري فقط لـ XTTS والمحركات الضخمة. يُسمح بـ HTTP داخل الشبكة المحلية، ويلزم HTTPS لأي عنوان خارجي.',
                style: TextStyle(fontSize: 12),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        SectionCard(
          title: 'المظهر ووضع التشغيل',
          icon: Icons.tune_rounded,
          child: Column(
            children: <Widget>[
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: appState.themeMode == ThemeMode.dark,
                title: const Text('الوضع الداكن'),
                onChanged: (value) => ref
                    .read(appControllerProvider.notifier)
                    .setTheme(value ? ThemeMode.dark : ThemeMode.light),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: appState.localMode || appState.session == null,
                title: const Text('الوضع المحلي المستقل'),
                subtitle: const Text(
                  'التسجيل والمعاينة وFFmpeg والتحليل والتحويل وتوليد الصوت العربي وقراءة المستندات على الهاتف.',
                ),
                onChanged: appState.session == null
                    ? null
                    : (value) => ref
                        .read(appControllerProvider.notifier)
                        .setLocalMode(value),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        SectionCard(
          title: 'محرك الصوت العربي على الهاتف',
          icon: Icons.record_voice_over_rounded,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: _checkingVoice
                    ? const SizedBox(
                        width: 28,
                        height: 28,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Icon(
                        _voiceStatus?.installed == true
                            ? Icons.check_circle_rounded
                            : Icons.download_for_offline_rounded,
                        color: _voiceStatus?.installed == true
                            ? Colors.green
                            : Colors.orange,
                      ),
                title: Text(
                  _voiceStatus?.installed == true
                      ? 'الصوت العربي المحلي جاهز'
                      : 'يلزم تجهيز الصوت العربي',
                ),
                subtitle: Text(
                  _voiceStatus?.message ??
                      'اضغط الفحص لمعرفة حالة محرك Android.',
                ),
              ),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: <Widget>[
                  FilledButton.tonalIcon(
                    onPressed: _checkingVoice ? null : _checkLocalVoice,
                    icon: const Icon(Icons.refresh_rounded),
                    label: const Text('فحص المحرك'),
                  ),
                  FilledButton.icon(
                    onPressed: () =>
                        ref.read(localTtsServiceProvider).installVoiceData(),
                    icon: const Icon(Icons.download_rounded),
                    label: const Text('تنزيل الصوت العربي'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () =>
                        ref.read(localTtsServiceProvider).openSystemSettings(),
                    icon: const Icon(Icons.settings_voice_rounded),
                    label: const Text('إعدادات الصوت'),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        SectionCard(
          title: 'Gemini وElevenLabs — اتصال مباشر',
          icon: Icons.key_rounded,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              const Text(
                'تعمل الخدمتان مباشرة من الهاتف دون خادم وسيط أو QR. الفحص الحقيقي يتحقق من المفتاح والنماذج ثم يولّد عينة صوت قصيرة فعلية. تُحفظ المفاتيح مشفرة في Android Keystore.',
              ),
              const SizedBox(height: 6),
              const Text(
                'ملاحظة: عينة الفحص قد تُحتسب ضمن استخدام حساب المزود.',
                style: TextStyle(fontSize: 12),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _geminiKey,
                obscureText: !_showSecrets,
                enableSuggestions: false,
                autocorrect: false,
                textDirection: TextDirection.ltr,
                decoration: const InputDecoration(labelText: 'Gemini API Key'),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _geminiModel,
                textDirection: TextDirection.ltr,
                decoration: const InputDecoration(
                  labelText: 'Gemini TTS Model',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _geminiTextModel,
                textDirection: TextDirection.ltr,
                decoration: const InputDecoration(
                  labelText: 'Gemini Audio/STT Model',
                  helperText: 'لتحويل التسجيلات إلى نص وتحليل الصوت',
                ),
              ),
              const SizedBox(height: 10),
              DropdownButtonFormField<String>(
                initialValue: _geminiVoice,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'صوت Gemini الافتراضي',
                ),
                items: CloudProviderService.geminiVoices
                    .map(
                      (voice) => DropdownMenuItem<String>(
                        value: voice,
                        child: Text(voice, textDirection: TextDirection.ltr),
                      ),
                    )
                    .toList(),
                onChanged: (value) =>
                    setState(() => _geminiVoice = value ?? 'Kore'),
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: _testingGemini ? null : _testGemini,
                icon: _testingGemini
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.cloud_done_rounded),
                label: const Text('فحص Gemini الحقيقي وتوليد عينة'),
              ),
              if (_geminiStatus != null)
                _providerStatusTile(_geminiStatus!),
              const SizedBox(height: 10),
              TextField(
                controller: _elevenLabsKey,
                obscureText: !_showSecrets,
                enableSuggestions: false,
                autocorrect: false,
                textDirection: TextDirection.ltr,
                decoration: const InputDecoration(
                  labelText: 'ElevenLabs API Key',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _elevenLabsModel,
                textDirection: TextDirection.ltr,
                decoration: const InputDecoration(
                  labelText: 'ElevenLabs Model',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _elevenLabsStsModel,
                textDirection: TextDirection.ltr,
                decoration: const InputDecoration(
                  labelText: 'ElevenLabs Voice Changer Model',
                ),
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: _testingElevenLabs ? null : _testElevenLabs,
                icon: _testingElevenLabs
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.cloud_done_rounded),
                label: const Text('فحص ElevenLabs الحقيقي وتوليد عينة'),
              ),
              if (_elevenLabsStatus != null)
                Column(
                  children: <Widget>[
                    _providerStatusTile(_elevenLabsStatus!),
                    if (_elevenLabsStatus!.available)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('تفاصيل حساب ElevenLabs'),
                        subtitle: Text(
                          <String>[
                            if (_elevenLabsStatus!.plan != null)
                              'الخطة: ${_elevenLabsStatus!.plan}',
                            if (_elevenLabsStatus!.remainingCharacters != null)
                              'المتبقي: ${_elevenLabsStatus!.remainingCharacters} حرف',
                            if (_elevenLabsStatus!.canCloneVoice != null)
                              _elevenLabsStatus!.canCloneVoice!
                                  ? 'الاستنساخ الفوري متاح'
                                  : 'الاستنساخ غير متاح في الخطة الحالية',
                          ].join(' • '),
                        ),
                      ),
                  ],
                ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _showSecrets,
                onChanged: (value) =>
                    setState(() => _showSecrets = value ?? false),
                title: const Text('إظهار المفاتيح على هذه الشاشة مؤقتًا'),
              ),
              FilledButton.icon(
                onPressed: _saving ? null : _save,
                icon: _saving
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.lock_rounded),
                label: const Text('حفظ الإعدادات بأمان'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 90),
      ],
    );
  }
}
