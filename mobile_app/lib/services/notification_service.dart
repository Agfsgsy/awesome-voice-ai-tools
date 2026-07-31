import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:voice_ai_mobile/core/constants/app_constants.dart';

class NotificationService {
  NotificationService({FlutterLocalNotificationsPlugin? plugin})
      : _plugin = plugin ?? FlutterLocalNotificationsPlugin();

  final FlutterLocalNotificationsPlugin _plugin;
  bool _initialized = false;

  Future<void> initialize() async {
    if (_initialized) return;
    await _plugin.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@drawable/ic_mic_notification'),
        iOS: DarwinInitializationSettings(),
      ),
    );
    _initialized = true;
  }

  Future<void> requestPermission() async {
    await initialize();
    if (await Permission.notification.isDenied) await Permission.notification.request();
  }

  Future<void> showProgress(String jobId, String message, int progress) async {
    await initialize();
    await _plugin.show(
      id: jobId.hashCode & 0x7fffffff,
      title: AppConstants.appName,
      body: message,
      notificationDetails: NotificationDetails(
        android: AndroidNotificationDetails(
          'long_jobs',
          'العمليات الطويلة',
          channelDescription: 'تقدم تنزيل النماذج وتوليد الصوت',
          importance: Importance.low,
          priority: Priority.low,
          onlyAlertOnce: true,
          showProgress: true,
          maxProgress: 100,
          progress: progress,
          ongoing: progress < 100,
        ),
        iOS: const DarwinNotificationDetails(presentSound: false),
      ),
    );
  }

  Future<void> showCompleted(String jobId, String message) async {
    await initialize();
    await _plugin.show(
      id: jobId.hashCode & 0x7fffffff,
      title: 'اكتملت العملية',
      body: message,
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails('completed_jobs', 'العمليات المكتملة', importance: Importance.high),
        iOS: DarwinNotificationDetails(),
      ),
    );
  }
}
