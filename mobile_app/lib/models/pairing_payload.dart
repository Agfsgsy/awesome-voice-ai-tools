import 'package:voice_ai_mobile/core/errors/app_exception.dart';

class PairingPayload {
  const PairingPayload({required this.serverUrl, required this.pairingId, required this.code});

  final String serverUrl;
  final String pairingId;
  final String code;

  factory PairingPayload.parse(String raw) {
    final uri = Uri.tryParse(raw);
    if (uri == null || uri.scheme != 'voiceai' || uri.host != 'pair') {
      throw const AppException('رمز QR ليس رمز اقتران صالحًا لـ Voice AI Studio.');
    }
    final server = uri.queryParameters['server'];
    final id = uri.queryParameters['id'];
    final code = uri.queryParameters['code'];
    if (server == null || server.isEmpty || id == null || id.length < 10 || code == null || code.length < 8) {
      throw const AppException('رمز QR ناقص أو انتهت جلسة الاقتران.');
    }
    return PairingPayload(serverUrl: server, pairingId: id, code: code.toUpperCase());
  }
}
