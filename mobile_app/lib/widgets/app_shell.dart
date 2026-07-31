import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';

class _Destination {
  const _Destination(this.path, this.label, this.icon);

  final String path;
  final String label;
  final IconData icon;
}

const _destinations = <_Destination>[
  _Destination('/dashboard', 'لوحة التحكم', Icons.dashboard_rounded),
  _Destination('/studio', 'توليد الصوت', Icons.graphic_eq_rounded),
  _Destination('/record', 'التسجيل والتحليل', Icons.mic_rounded),
  _Destination('/clone', 'استنساخ الصوت Pro', Icons.record_voice_over_rounded),
  _Destination('/documents', 'قارئ المستندات', Icons.menu_book_rounded),
  _Destination('/songs', 'استوديو الشيلات', Icons.library_music_rounded),
  _Destination('/files', 'المشاريع والملفات', Icons.folder_copy_rounded),
  _Destination('/engines', 'المحركات والنماذج', Icons.memory_rounded),
  _Destination('/settings', 'الإعدادات', Icons.settings_rounded),
];

class AppShell extends ConsumerWidget {
  const AppShell({required this.location, required this.child, super.key});

  final String location;
  final Widget child;

  int get _index {
    final index = _destinations.indexWhere((destination) => location.startsWith(destination.path));
    return index < 0 ? 0 : index;
  }

  void _go(BuildContext context, int index) => context.go(_destinations[index].path);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final appState = ref.watch(appControllerProvider);
    final width = MediaQuery.sizeOf(context).width;
    final useRail = width >= 760;
    final title = _destinations[_index].label;
    final body = SafeArea(
      child: Row(
        children: <Widget>[
          if (useRail)
            NavigationRail(
              selectedIndex: _index,
              scrollable: true,
              extended: width >= 1180,
              minExtendedWidth: 230,
              labelType: width >= 1180 ? NavigationRailLabelType.none : NavigationRailLabelType.selected,
              leading: const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Icon(Icons.mic_external_on_rounded, color: Color(0xFF14B8A6), size: 32),
              ),
              destinations: _destinations
                  .map((destination) => NavigationRailDestination(icon: Icon(destination.icon), label: Text(destination.label)))
                  .toList(),
              onDestinationSelected: (index) => _go(context, index),
            ),
          Expanded(child: child),
        ],
      ),
    );
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: <Widget>[
          Padding(
            padding: const EdgeInsetsDirectional.only(end: 4),
            child: Tooltip(
              message: appState.online ? 'الخادم متصل' : (appState.localMode ? 'الوضع المحلي' : 'الخادم غير متصل'),
              child: Chip(
                avatar: Icon(
                  appState.online ? Icons.cloud_done_rounded : (appState.localMode ? Icons.phone_android_rounded : Icons.cloud_off_rounded),
                  size: 18,
                  color: appState.online ? Colors.green : Colors.orange,
                ),
                label: Text(appState.online ? 'متصل' : (appState.localMode ? 'محلي' : 'غير متصل')),
              ),
            ),
          ),
          IconButton(
            tooltip: 'تبديل المظهر',
            onPressed: () => ref
                .read(appControllerProvider.notifier)
                .setTheme(appState.themeMode == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark),
            icon: Icon(appState.themeMode == ThemeMode.dark ? Icons.light_mode_rounded : Icons.dark_mode_rounded),
          ),
        ],
      ),
      drawer: useRail
          ? null
          : NavigationDrawer(
              selectedIndex: _index,
              onDestinationSelected: (index) {
                Navigator.pop(context);
                _go(context, index);
              },
              children: <Widget>[
                const Padding(
                  padding: EdgeInsets.fromLTRB(24, 28, 24, 18),
                  child: Text('🎙️ Voice AI Studio', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                ),
                ..._destinations.map(
                  (destination) => NavigationDrawerDestination(icon: Icon(destination.icon), label: Text(destination.label)),
                ),
              ],
            ),
      body: body,
      bottomNavigationBar: useRail
          ? null
          : NavigationBar(
              selectedIndex: switch (_index) { 1 => 1, 2 => 2, 6 => 3, _ => 0 },
              onDestinationSelected: (index) => _go(context, <int>[0, 1, 2, 6][index]),
              destinations: const <NavigationDestination>[
                NavigationDestination(icon: Icon(Icons.dashboard_rounded), label: 'الرئيسية'),
                NavigationDestination(icon: Icon(Icons.graphic_eq_rounded), label: 'الاستوديو'),
                NavigationDestination(icon: Icon(Icons.mic_rounded), label: 'تسجيل'),
                NavigationDestination(icon: Icon(Icons.folder_rounded), label: 'الملفات'),
              ],
            ),
    );
  }
}
