import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';

class SplashScreen extends ConsumerWidget {
  const SplashScreen({super.key});

  void _route(BuildContext context, AppState state) {
    if (!state.initialized) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!context.mounted) return;
      context.go(state.session != null || state.localMode ? '/dashboard' : '/pair');
    });
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(appControllerProvider);
    ref.listen<AppState>(appControllerProvider, (previous, next) => _route(context, next));
    _route(context, state);
    return const Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.mic_external_on_rounded, size: 76, color: Color(0xFF14B8A6)),
            SizedBox(height: 16),
            Text('Voice AI Studio', style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold)),
            SizedBox(height: 24),
            CircularProgressIndicator(),
          ],
        ),
      ),
    );
  }
}
