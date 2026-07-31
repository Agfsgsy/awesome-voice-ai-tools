import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final _geminiKey = TextEditingController();
  final _geminiModel = TextEditingController(text: 'gemini-3.1-flash-tts-preview');
  final _elevenLabsKey = TextEditingController();
  final _elevenLabsModel = TextEditingController(text: 'eleven_multilingual_v2');
  bool _loading = true;
  bool _saving = false;
  bool _showSecrets = false;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_load);
  }

  @override
  void dispose() {
    _geminiKey.dispose();
    _geminiModel.dispose();
    _elevenLabsKey.dispose();
    _elevenLabsModel.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final storage = ref.read(secureStorageProvider);
    _geminiKey.text = await storage.readSecret('gemini_api_key') ?? '';
    _geminiModel.text = await storage.readSecret('gemini_model') ?? _geminiModel.text;
    _elevenLabsKey.text = await storage.readSecret('elevenlabs_api_key') ?? '';
    _elevenLabsModel.text = await storage.readSecret('elevenlabs_model') ?? _elevenLabsModel.text;
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final storage = ref.read(secureStorageProvider);
    await storage.writeSecret('gemini_api_key', _geminiKey.text);
    await storage.writeSecret('gemini_model', _geminiModel.text);
    await storage.writeSecret('elevenlabs_api_key', _elevenLabsKey.text);
    await storage.writeSecret('elevenlabs_model', _elevenLabsModel.text);
    ref.invalidate(providerHeadersProvider);
    if (mounted) {
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('حُفظت الإعدادات مشفرة داخل مخزن النظام الآمن.')));
    }
  }

  Future<void> _disconnect() async {
    await ref.read(appControllerProvider.notifier).disconnect();
    if (mounted) context.go('/pair');
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    final appState = ref.watch(appControllerProvider);
    return ResponsivePage(
      children: <Widget>[
        SectionCard(
          title: 'الاتصال بالخادم',
          icon: Icons.dns_rounded,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(appState.online ? Icons.cloud_done_rounded : Icons.cloud_off_rounded, color: appState.online ? Colors.green : Colors.orange),
                title: Text(appState.online ? 'الخادم متصل' : 'الخادم غير متصل'),
                subtitle: Text(appState.session?.serverUrl ?? 'لم يُقترن هذا الهاتف بخادم', textDirection: TextDirection.ltr),
                trailing: IconButton(tooltip: 'اختبار الاتصال', onPressed: () => ref.read(appControllerProvider.notifier).checkConnection(), icon: const Icon(Icons.refresh_rounded)),
              ),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: <Widget>[
                  FilledButton.tonalIcon(onPressed: () => context.go('/pair'), icon: const Icon(Icons.qr_code_scanner_rounded), label: Text(appState.session == null ? 'اقتران بخادم' : 'إعادة الاقتران بخادم آخر')),
                  if (appState.session != null) OutlinedButton.icon(onPressed: _disconnect, icon: const Icon(Icons.link_off_rounded), label: const Text('فصل هذا الهاتف')),
                ],
              ),
              const SizedBox(height: 8),
              const Text('يُسمح بـ HTTP لعناوين الشبكة المحلية فقط. يلزم HTTPS لأي عنوان خارجي.', style: TextStyle(fontSize: 12)),
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
                onChanged: (value) => ref.read(appControllerProvider.notifier).setTheme(value ? ThemeMode.dark : ThemeMode.light),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: appState.localMode,
                title: const Text('تفعيل الأدوات المحلية الخفيفة'),
                subtitle: const Text('التسجيل والمعاينة والتحليل والتحويل على الهاتف؛ تبقى XTTS والمحركات الثقيلة على الخادم.'),
                onChanged: (value) => ref.read(appControllerProvider.notifier).setLocalMode(value),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        SectionCard(
          title: 'Gemini وElevenLabs',
          icon: Icons.key_rounded,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              const Text('لا تُخزن المفاتيح في الكود أو الخادم. تُحفظ مشفرة في Android Keystore وتُرسل عبر HTTPS فقط عند استخدام المحرك.'),
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
              TextField(controller: _geminiModel, textDirection: TextDirection.ltr, decoration: const InputDecoration(labelText: 'Gemini TTS Model')),
              const SizedBox(height: 10),
              TextField(
                controller: _elevenLabsKey,
                obscureText: !_showSecrets,
                enableSuggestions: false,
                autocorrect: false,
                textDirection: TextDirection.ltr,
                decoration: const InputDecoration(labelText: 'ElevenLabs API Key'),
              ),
              const SizedBox(height: 10),
              TextField(controller: _elevenLabsModel, textDirection: TextDirection.ltr, decoration: const InputDecoration(labelText: 'ElevenLabs Model')),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _showSecrets,
                onChanged: (value) => setState(() => _showSecrets = value ?? false),
                title: const Text('إظهار المفاتيح على هذه الشاشة مؤقتًا'),
              ),
              FilledButton.icon(
                onPressed: _saving ? null : _save,
                icon: _saving ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.lock_rounded),
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
