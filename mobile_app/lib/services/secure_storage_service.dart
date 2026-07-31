import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:voice_ai_mobile/models/server_session.dart';

class SecureStorageService {
  SecureStorageService({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
              iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
            );

  final FlutterSecureStorage _storage;

  static const _sessionKeys = <String>{
    'server_url',
    'device_id',
    'device_token',
    'access_token',
    'expires_at',
  };

  Future<ServerSession?> readSession() async {
    final values = <String, String>{};
    for (final key in _sessionKeys) {
      final value = await _storage.read(key: key);
      if (value == null || value.isEmpty) return null;
      values[key] = value;
    }
    try {
      return ServerSession.fromMap(values);
    } on Object {
      await clearSession();
      return null;
    }
  }

  Future<void> saveSession(ServerSession session) async {
    for (final entry in session.toMap().entries) {
      await _storage.write(key: entry.key, value: entry.value);
    }
  }

  Future<void> clearSession() async {
    for (final key in _sessionKeys) {
      await _storage.delete(key: key);
    }
  }

  Future<void> writeSecret(String key, String value) async {
    if (value.trim().isEmpty) {
      await _storage.delete(key: key);
    } else {
      await _storage.write(key: key, value: value.trim());
    }
  }

  Future<String?> readSecret(String key) => _storage.read(key: key);

  Future<void> savePendingJobs(Iterable<String> jobIds) =>
      _storage.write(key: 'pending_jobs', value: jsonEncode(jobIds.toList()));

  Future<List<String>> readPendingJobs() async {
    final raw = await _storage.read(key: 'pending_jobs');
    if (raw == null) return const <String>[];
    try {
      return (jsonDecode(raw) as List<dynamic>).cast<String>();
    } on Object {
      return const <String>[];
    }
  }

  Future<void> writePreference(String key, String value) => _storage.write(key: 'pref_$key', value: value);

  Future<String?> readPreference(String key) => _storage.read(key: 'pref_$key');
}
