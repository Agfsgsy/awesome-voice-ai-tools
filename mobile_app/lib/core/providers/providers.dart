import 'dart:async';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:voice_ai_mobile/core/constants/app_constants.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';
import 'package:voice_ai_mobile/models/cloud_provider_models.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/models/server_session.dart';
import 'package:voice_ai_mobile/services/api_service.dart';
import 'package:voice_ai_mobile/services/audio_player_service.dart';
import 'package:voice_ai_mobile/services/audio_recorder_service.dart';
import 'package:voice_ai_mobile/services/cloud_provider_service.dart';
import 'package:voice_ai_mobile/services/document_picker_service.dart';
import 'package:voice_ai_mobile/services/local_audio_service.dart';
import 'package:voice_ai_mobile/services/local_document_service.dart';
import 'package:voice_ai_mobile/services/local_tts_service.dart';
import 'package:voice_ai_mobile/services/notification_service.dart';
import 'package:voice_ai_mobile/services/project_service.dart';
import 'package:voice_ai_mobile/services/secure_storage_service.dart';
import 'package:voice_ai_mobile/services/server_discovery_service.dart';

final secureStorageProvider = Provider<SecureStorageService>(
  (ref) => SecureStorageService(),
);
final apiServiceProvider = Provider<ApiService>((ref) => ApiService());
final cloudProviderServiceProvider = Provider<CloudProviderService>(
  (ref) => CloudProviderService(),
);
final recorderServiceProvider = Provider<AudioRecorderService>((ref) {
  final service = AudioRecorderService();
  ref.onDispose(service.dispose);
  return service;
});
final playerServiceProvider = Provider<AudioPlayerService>((ref) {
  final service = AudioPlayerService();
  ref.onDispose(service.dispose);
  return service;
});
final localAudioServiceProvider = Provider<LocalAudioService>(
  (ref) => LocalAudioService(),
);
final localDocumentServiceProvider = Provider<LocalDocumentService>(
  (ref) => LocalDocumentService(),
);
final localTtsServiceProvider = Provider<LocalTtsService>((ref) {
  final service = LocalTtsService();
  ref.onDispose(service.dispose);
  return service;
});
final documentPickerProvider = Provider<DocumentPickerService>(
  (ref) => DocumentPickerService(),
);
final notificationServiceProvider = Provider<NotificationService>(
  (ref) => NotificationService(),
);
final discoveryServiceProvider = Provider<ServerDiscoveryService>(
  (ref) => ServerDiscoveryService(),
);
final projectServiceProvider = Provider<ProjectService>(
  (ref) => ProjectService(),
);
final connectivityProvider = Provider<Connectivity>((ref) => Connectivity());

final cloudProviderConfigProvider = FutureProvider<CloudProviderConfig>((
  ref,
) async {
  final storage = ref.watch(secureStorageProvider);
  return CloudProviderConfig(
    geminiApiKey: await storage.readSecret('gemini_api_key') ?? '',
    geminiModel: await storage.readSecret('gemini_model') ??
        'gemini-3.1-flash-tts-preview',
    geminiVoice: await storage.readSecret('gemini_voice') ?? 'Kore',
    geminiTextModel:
        await storage.readSecret('gemini_text_model') ?? 'gemini-3.6-flash',
    elevenLabsApiKey: await storage.readSecret('elevenlabs_api_key') ?? '',
    elevenLabsModel: await storage.readSecret('elevenlabs_model') ??
        'eleven_multilingual_v2',
    elevenLabsStsModel: await storage.readSecret('elevenlabs_sts_model') ??
        'eleven_multilingual_sts_v2',
  );
});

class AppState {
  const AppState({
    this.initialized = false,
    this.busy = false,
    this.online = false,
    this.localMode = true,
    this.themeMode = ThemeMode.dark,
    this.session,
    this.error,
  });

  final bool initialized;
  final bool busy;
  final bool online;
  final bool localMode;
  final ThemeMode themeMode;
  final ServerSession? session;
  final String? error;

  AppState copyWith({
    bool? initialized,
    bool? busy,
    bool? online,
    bool? localMode,
    ThemeMode? themeMode,
    ServerSession? session,
    bool clearSession = false,
    String? error,
    bool clearError = false,
  }) =>
      AppState(
        initialized: initialized ?? this.initialized,
        busy: busy ?? this.busy,
        online: online ?? this.online,
        localMode: localMode ?? this.localMode,
        themeMode: themeMode ?? this.themeMode,
        session: clearSession ? null : (session ?? this.session),
        error: clearError ? null : (error ?? this.error),
      );
}

class AppController extends StateNotifier<AppState> {
  AppController(
    this._storage,
    this._api,
    this._connectivity,
    this._notifications, {
    bool autoInitialize = true,
  }) : super(const AppState()) {
    if (autoInitialize) unawaited(initialize());
  }

  final SecureStorageService _storage;
  final ApiService _api;
  final Connectivity _connectivity;
  final NotificationService _notifications;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;
  Future<String?>? _refreshing;

  Future<void> initialize() async {
    final theme = await _storage.readPreference('theme');
    final session = await _storage.readSession();
    final local = session == null ||
        await _storage.readPreference('local_mode') == 'true';
    if (session == null) await _storage.writePreference('local_mode', 'true');
    state = state.copyWith(
      themeMode: theme == 'light' ? ThemeMode.light : ThemeMode.dark,
      localMode: local,
      session: session,
      clearError: true,
    );
    if (session != null) {
      _api.configure(
        serverUrl: session.serverUrl,
        accessToken: session.accessToken,
        refresh: refreshAccessToken,
      );
      try {
        if (session.expiresAt.isBefore(
          DateTime.now().add(const Duration(minutes: 2)),
        )) {
          await refreshAccessToken();
        }
        await _api.status();
        state = state.copyWith(online: true);
      } on Object {
        state = state.copyWith(online: false);
      }
    }
    await _notifications.initialize();
    _connectivitySubscription = _connectivity.onConnectivityChanged.listen((
      results,
    ) {
      final connected = results.any(
        (result) => result != ConnectivityResult.none,
      );
      if (!connected && state.session != null) {
        state = state.copyWith(
          online: false,
          error: 'انقطع الإنترنت. ستُستأنف المهام عند عودة الاتصال.',
        );
      } else if (state.session != null) {
        unawaited(checkConnection());
      } else {
        state = state.copyWith(online: false, clearError: true);
      }
    });
    state = state.copyWith(initialized: true);
  }

  Future<void> pair({
    required String serverUrl,
    required String pairingId,
    required String pairingCode,
  }) async {
    state = state.copyWith(busy: true, clearError: true);
    try {
      final session = await _api.pair(
        serverUrl: serverUrl,
        pairingId: pairingId,
        pairingCode: pairingCode,
        deviceName: PlatformName.deviceName,
      );
      await _storage.saveSession(session);
      _api.configure(
        serverUrl: session.serverUrl,
        accessToken: session.accessToken,
        refresh: refreshAccessToken,
      );
      state = state.copyWith(
        session: session,
        online: true,
        busy: false,
        localMode: false,
      );
      await _storage.writePreference('local_mode', 'false');
      await _notifications.requestPermission();
    } on AppException catch (error) {
      state = state.copyWith(busy: false, error: error.message);
      rethrow;
    }
  }

  Future<String?> refreshAccessToken() {
    final active = _refreshing;
    if (active != null) return active;
    final completer = _refreshSession();
    _refreshing = completer;
    return completer.whenComplete(() => _refreshing = null);
  }

  Future<String?> _refreshSession() async {
    final session = state.session;
    if (session == null) return null;
    try {
      final result = await _api.authenticate(
        session.deviceId,
        session.deviceToken,
      );
      final updated = session.copyWith(
        accessToken: result['access_token'] as String,
        expiresAt: DateTime.parse(result['expires_at'] as String),
      );
      await _storage.saveSession(updated);
      _api.updateToken(updated.accessToken);
      state = state.copyWith(session: updated, online: true, clearError: true);
      return updated.accessToken;
    } on AppException catch (error) {
      state = state.copyWith(online: false, error: error.message);
      return null;
    }
  }

  Future<bool> checkConnection() async {
    if (state.session == null) return false;
    try {
      await _api.status();
      state = state.copyWith(online: true, clearError: true);
      return true;
    } on AppException catch (error) {
      state = state.copyWith(online: false, error: error.message);
      return false;
    }
  }

  Future<void> setTheme(ThemeMode mode) async {
    state = state.copyWith(themeMode: mode);
    await _storage.writePreference(
      'theme',
      mode == ThemeMode.light ? 'light' : 'dark',
    );
  }

  Future<void> setLocalMode(bool value) async {
    final enabled = state.session == null || value;
    state = state.copyWith(localMode: enabled, clearError: enabled);
    await _storage.writePreference('local_mode', enabled.toString());
  }

  Future<void> disconnect() async {
    await _storage.clearSession();
    _api.configure(serverUrl: 'http://localhost');
    await _storage.writePreference('local_mode', 'true');
    state = state.copyWith(
      clearSession: true,
      online: false,
      localMode: true,
      clearError: true,
    );
  }

  @override
  void dispose() {
    unawaited(_connectivitySubscription?.cancel());
    super.dispose();
  }
}

abstract final class PlatformName {
  static String get deviceName {
    final name = Platform.localHostname.trim();
    return name.isEmpty ? 'هاتف Android' : name;
  }
}

final appControllerProvider = StateNotifierProvider<AppController, AppState>((
  ref,
) {
  return AppController(
    ref.watch(secureStorageProvider),
    ref.watch(apiServiceProvider),
    ref.watch(connectivityProvider),
    ref.watch(notificationServiceProvider),
  );
});

class JobController extends StateNotifier<Map<String, MobileJob>> {
  JobController(this._api, this._storage, this._notifications)
      : super(const <String, MobileJob>{}) {
    unawaited(_restore());
  }

  final ApiService _api;
  final SecureStorageService _storage;
  final NotificationService _notifications;
  final Set<String> _polling = <String>{};
  bool _disposed = false;

  Future<void> _restore() async {
    for (final id in await _storage.readPendingJobs()) {
      unawaited(resume(id));
    }
  }

  Future<void> track(MobileJob job) async {
    state = <String, MobileJob>{...state, job.id: job};
    await _persist();
    unawaited(_poll(job.id));
  }

  Future<void> resume(String id) async {
    try {
      final current = await _api.job(id);
      state = <String, MobileJob>{...state, id: current};
      if (current.finished) {
        await _persist();
      } else {
        unawaited(_poll(id));
      }
    } on AppException {
      // تبقى هوية المهمة محفوظة لمحاولة الاستئناف التالية.
    }
  }

  Future<void> _poll(String id) async {
    if (!_polling.add(id)) return;
    var retryDelay = AppConstants.jobPollInterval;
    try {
      while (!_disposed) {
        try {
          final current = await _api.job(id);
          state = <String, MobileJob>{...state, id: current};
          await _notifications.showProgress(
            id,
            current.message,
            current.progress,
          );
          if (current.finished) {
            await _notifications.showCompleted(id, current.message);
            await _persist();
            return;
          }
          retryDelay = AppConstants.jobPollInterval;
        } on AppException catch (error) {
          if (!error.retryable) return;
          retryDelay = Duration(
            seconds: (retryDelay.inSeconds * 2).clamp(2, 30),
          );
        }
        await Future<void>.delayed(retryDelay);
      }
    } finally {
      _polling.remove(id);
    }
  }

  Future<void> cancel(String id) async {
    final cancelled = await _api.cancelJob(id);
    state = <String, MobileJob>{...state, id: cancelled};
    await _persist();
  }

  Future<void> dismiss(String id) async {
    final updated = <String, MobileJob>{...state}..remove(id);
    state = updated;
    await _persist();
  }

  Future<void> _persist() => _storage.savePendingJobs(
        state.values.where((job) => !job.finished).map((job) => job.id),
      );

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

final jobControllerProvider =
    StateNotifierProvider<JobController, Map<String, MobileJob>>((ref) {
  return JobController(
    ref.watch(apiServiceProvider),
    ref.watch(secureStorageProvider),
    ref.watch(notificationServiceProvider),
  );
});

final selectedReferenceProvider = StateProvider<SelectedReference?>(
  (ref) => null,
);

final providerHeadersProvider = FutureProvider<Map<String, String>>((
  ref,
) async {
  final storage = ref.watch(secureStorageProvider);
  final api = ref.watch(apiServiceProvider);
  return api.providerHeaders(
    geminiKey: await storage.readSecret('gemini_api_key'),
    geminiModel: await storage.readSecret('gemini_model'),
    elevenLabsKey: await storage.readSecret('elevenlabs_api_key'),
    elevenLabsModel: await storage.readSecret('elevenlabs_model'),
  );
});
