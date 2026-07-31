import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:voice_ai_mobile/features/dashboard/dashboard_screen.dart';
import 'package:voice_ai_mobile/features/documents/document_reader_screen.dart';
import 'package:voice_ai_mobile/features/engines/engines_screen.dart';
import 'package:voice_ai_mobile/features/files/files_screen.dart';
import 'package:voice_ai_mobile/features/onboarding/pairing_screen.dart';
import 'package:voice_ai_mobile/features/onboarding/splash_screen.dart';
import 'package:voice_ai_mobile/features/recorder/recorder_screen.dart';
import 'package:voice_ai_mobile/features/settings/settings_screen.dart';
import 'package:voice_ai_mobile/features/songs/song_studio_screen.dart';
import 'package:voice_ai_mobile/features/voice_clone/voice_clone_screen.dart';
import 'package:voice_ai_mobile/features/voice_studio/voice_studio_screen.dart';
import 'package:voice_ai_mobile/widgets/app_shell.dart';

final appRouter = GoRouter(
  initialLocation: '/splash',
  routes: <RouteBase>[
    GoRoute(path: '/splash', builder: (context, state) => const SplashScreen()),
    GoRoute(path: '/pair', builder: (context, state) => const PairingScreen()),
    ShellRoute(
      builder: (context, state, child) => AppShell(location: state.uri.path, child: child),
      routes: <RouteBase>[
        GoRoute(path: '/dashboard', builder: (context, state) => const DashboardScreen()),
        GoRoute(path: '/studio', builder: (context, state) => const VoiceStudioScreen()),
        GoRoute(path: '/record', builder: (context, state) => const RecorderScreen()),
        GoRoute(path: '/clone', builder: (context, state) => const VoiceCloneScreen()),
        GoRoute(path: '/documents', builder: (context, state) => const DocumentReaderScreen()),
        GoRoute(path: '/songs', builder: (context, state) => const SongStudioScreen()),
        GoRoute(path: '/files', builder: (context, state) => const FilesScreen()),
        GoRoute(path: '/engines', builder: (context, state) => const EnginesScreen()),
        GoRoute(path: '/settings', builder: (context, state) => const SettingsScreen()),
      ],
    ),
  ],
  errorBuilder: (context, state) => Scaffold(
    body: Center(child: Text('الصفحة غير موجودة: ${state.uri.path}')),
  ),
);
