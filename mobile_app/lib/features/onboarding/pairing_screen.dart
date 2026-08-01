import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/pairing_payload.dart';
import 'package:voice_ai_mobile/services/server_discovery_service.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';

class PairingScreen extends ConsumerStatefulWidget {
  const PairingScreen({super.key});

  @override
  ConsumerState<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends ConsumerState<PairingScreen> {
  final _formKey = GlobalKey<FormState>();
  final _serverController = TextEditingController();
  final _pairingIdController = TextEditingController();
  final _codeController = TextEditingController();
  bool _discovering = false;

  @override
  void dispose() {
    _serverController.dispose();
    _pairingIdController.dispose();
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _pair() async {
    if (!_formKey.currentState!.validate()) return;
    try {
      await ref
          .read(appControllerProvider.notifier)
          .pair(
            serverUrl: _serverController.text,
            pairingId: _pairingIdController.text.trim(),
            pairingCode: _codeController.text.trim().toUpperCase(),
          );
      if (mounted) context.go('/dashboard');
    } on AppException {
      // تعرض الحالة رسالة الخادم المحددة أسفل النموذج.
    }
  }

  Future<void> _scanQr() async {
    final permission = await Permission.camera.request();
    if (!permission.isGranted) {
      if (mounted) {
        _showMessage(
          'يلزم السماح بالكاميرا لمسح رمز QR. ويمكن إدخال الرمز يدويًا.',
        );
      }
      return;
    }
    if (!mounted) return;
    final payload = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(builder: (context) => const _QrScannerPage()),
    );
    if (payload == null) return;
    try {
      final pairing = PairingPayload.parse(payload);
      setState(() {
        _serverController.text = pairing.serverUrl;
        _pairingIdController.text = pairing.pairingId;
        _codeController.text = pairing.code;
      });
      await _pair();
    } on AppException catch (error) {
      if (mounted) _showMessage(error.message);
    }
  }

  Future<void> _discover() async {
    setState(() => _discovering = true);
    final servers = await ref.read(discoveryServiceProvider).discover();
    if (!mounted) return;
    setState(() => _discovering = false);
    if (servers.isEmpty) {
      _showMessage(
        'لم يُعثر على خادم داخل الشبكة. تأكد أن الهاتف والكمبيوتر على الشبكة نفسها.',
      );
      return;
    }
    final selected = servers.length == 1
        ? servers.first
        : await _selectServer(servers);
    if (selected != null) setState(() => _serverController.text = selected.url);
  }

  Future<DiscoveredServer?> _selectServer(List<DiscoveredServer> servers) =>
      showDialog<DiscoveredServer>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('الخوادم المكتشفة'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: servers
                .map(
                  (server) => ListTile(
                    leading: const Icon(Icons.computer_rounded),
                    title: Text(server.name),
                    subtitle: Text(
                      server.url,
                      textDirection: TextDirection.ltr,
                    ),
                    onTap: () => Navigator.pop(context, server),
                  ),
                )
                .toList(),
          ),
        ),
      );

  void _showMessage(String message) => ScaffoldMessenger.of(
    context,
  ).showSnackBar(SnackBar(content: Text(message)));

  @override
  Widget build(BuildContext context) {
    final appState = ref.watch(appControllerProvider);
    return Scaffold(
      body: SafeArea(
        child: ResponsivePage(
          maxWidth: 620,
          padding: const EdgeInsets.all(24),
          children: <Widget>[
            const SizedBox(height: 24),
            const Icon(
              Icons.mic_external_on_rounded,
              size: 72,
              color: Color(0xFF14B8A6),
            ),
            const SizedBox(height: 12),
            Text(
              'Voice AI Studio على الهاتف',
              textAlign: TextAlign.center,
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            const Text(
              'سجّل وحلّل وحوّل الملفات واقرأ النصوص وأنشئ الصوت العربي مباشرة على الهاتف، دون كمبيوتر أو ربط.',
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            SectionCard(
              title: 'التشغيل المحلي المستقل',
              icon: Icons.offline_bolt_rounded,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  const Text(
                    'تعمل الأدوات الأساسية محليًا: التسجيل، اختيار الملفات، FFmpeg، تحليل الجودة، تحويل الصيغ، قارئ PDF وDOCX وTXT، وتوليد الصوت العربي من محرك Android.',
                  ),
                  const SizedBox(height: 14),
                  FilledButton.icon(
                    onPressed: () async {
                      await ref
                          .read(appControllerProvider.notifier)
                          .setLocalMode(true);
                      if (context.mounted) context.go('/dashboard');
                    },
                    icon: const Icon(Icons.phone_android_rounded),
                    label: const Text('ابدأ الآن من الهاتف'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            SectionCard(
              title: 'خادم اختياري للمحركات الثقيلة',
              icon: Icons.phonelink_lock_rounded,
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    TextFormField(
                      controller: _serverController,
                      textDirection: TextDirection.ltr,
                      keyboardType: TextInputType.url,
                      decoration: const InputDecoration(
                        labelText: 'عنوان الخادم',
                        hintText: 'http://voice-ai.local:8000',
                        prefixIcon: Icon(Icons.dns_rounded),
                      ),
                      validator: (value) =>
                          value == null || value.trim().isEmpty
                          ? 'أدخل عنوان الخادم'
                          : null,
                    ),
                    const SizedBox(height: 12),
                    OutlinedButton.icon(
                      onPressed: _discovering ? null : _discover,
                      icon: _discovering
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.radar_rounded),
                      label: const Text('البحث التلقائي داخل الشبكة'),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _pairingIdController,
                      textDirection: TextDirection.ltr,
                      decoration: const InputDecoration(
                        labelText: 'معرّف جلسة الاقتران',
                      ),
                      validator: (value) =>
                          value == null || value.trim().isEmpty
                          ? 'أدخل معرّف الجلسة أو امسح QR'
                          : null,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _codeController,
                      textDirection: TextDirection.ltr,
                      textCapitalization: TextCapitalization.characters,
                      decoration: const InputDecoration(
                        labelText: 'رمز الاقتران المؤقت',
                        hintText: 'ABCD-EFGH',
                      ),
                      validator: (value) =>
                          value == null || value.trim().length < 8
                          ? 'أدخل رمز الاقتران المؤقت'
                          : null,
                    ),
                    if (appState.error != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(
                          appState.error!,
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ),
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      onPressed: appState.busy ? null : _pair,
                      icon: appState.busy
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.link_rounded),
                      label: const Text('اقتران وتسجيل الدخول'),
                    ),
                    const SizedBox(height: 8),
                    FilledButton.tonalIcon(
                      onPressed: appState.busy ? null : _scanQr,
                      icon: const Icon(Icons.qr_code_scanner_rounded),
                      label: const Text('مسح رمز QR'),
                    ),
                  ],
                ),
              ),
            ),
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text(
                'الاقتران ليس مطلوبًا لتشغيل التطبيق. يُستخدم فقط عند اختيار XTTS أو خدمات سحابية أو نماذج أكبر من ذاكرة الهاتف.',
                textAlign: TextAlign.center,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _QrScannerPage extends StatefulWidget {
  const _QrScannerPage();

  @override
  State<_QrScannerPage> createState() => _QrScannerPageState();
}

class _QrScannerPageState extends State<_QrScannerPage> {
  final MobileScannerController _controller = MobileScannerController(
    formats: const <BarcodeFormat>[BarcodeFormat.qrCode],
  );
  bool _handled = false;

  @override
  void dispose() {
    unawaited(_controller.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('مسح رمز الاقتران')),
    body: Stack(
      fit: StackFit.expand,
      children: <Widget>[
        MobileScanner(
          controller: _controller,
          onDetect: (capture) {
            if (_handled || capture.barcodes.isEmpty) return;
            final value = capture.barcodes.first.rawValue;
            if (value == null) return;
            _handled = true;
            Navigator.pop(context, value);
          },
        ),
        Center(
          child: Container(
            width: 260,
            height: 260,
            decoration: BoxDecoration(
              border: Border.all(color: const Color(0xFF14B8A6), width: 3),
              borderRadius: BorderRadius.circular(20),
            ),
          ),
        ),
        const Align(
          alignment: Alignment.bottomCenter,
          child: SafeArea(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'وجّه الكاميرا نحو رمز QR الظاهر على الكمبيوتر',
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
            ),
          ),
        ),
      ],
    ),
  );
}
