class ServerSession {
  const ServerSession({
    required this.serverUrl,
    required this.deviceId,
    required this.deviceToken,
    required this.accessToken,
    required this.expiresAt,
  });

  final String serverUrl;
  final String deviceId;
  final String deviceToken;
  final String accessToken;
  final DateTime expiresAt;

  ServerSession copyWith({String? accessToken, DateTime? expiresAt}) => ServerSession(
        serverUrl: serverUrl,
        deviceId: deviceId,
        deviceToken: deviceToken,
        accessToken: accessToken ?? this.accessToken,
        expiresAt: expiresAt ?? this.expiresAt,
      );

  Map<String, String> toMap() => {
        'server_url': serverUrl,
        'device_id': deviceId,
        'device_token': deviceToken,
        'access_token': accessToken,
        'expires_at': expiresAt.toUtc().toIso8601String(),
      };

  factory ServerSession.fromMap(Map<String, String> value) => ServerSession(
        serverUrl: value['server_url']!,
        deviceId: value['device_id']!,
        deviceToken: value['device_token']!,
        accessToken: value['access_token']!,
        expiresAt: DateTime.parse(value['expires_at']!),
      );
}
