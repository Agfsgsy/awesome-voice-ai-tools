import 'dart:io';

import 'package:dio/dio.dart';

class AppException implements Exception {
  const AppException(this.message, {this.code, this.retryable = false});

  final String message;
  final String? code;
  final bool retryable;

  factory AppException.fromDio(DioException error) {
    final response = error.response;
    if (response != null) {
      final data = response.data;
      String? detail;
      if (data is Map<String, dynamic>) {
        final value = data['detail'];
        if (value is String) detail = value;
      }
      return AppException(
        detail ?? _statusMessage(response.statusCode),
        code: 'http_${response.statusCode}',
        retryable: response.statusCode == 408 || response.statusCode == 429 || (response.statusCode ?? 0) >= 500,
      );
    }
    if (error.error is SocketException ||
        error.type == DioExceptionType.connectionError ||
        error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.receiveTimeout ||
        error.type == DioExceptionType.sendTimeout) {
      return const AppException('الخادم غير متصل أو انقطع الإنترنت.', code: 'offline', retryable: true);
    }
    if (error.type == DioExceptionType.cancel) {
      return const AppException('المهمة أُلغيت.', code: 'cancelled');
    }
    return const AppException('تعذر إكمال الطلب. حاول مرة أخرى.', code: 'unknown', retryable: true);
  }

  static String _statusMessage(int? statusCode) => switch (statusCode) {
        400 => 'البيانات المرسلة غير صالحة.',
        401 => 'انتهت جلسة الدخول؛ أعد الاتصال بالخادم.',
        403 => 'ليس لديك إذن لتنفيذ هذه العملية.',
        404 => 'العنصر المطلوب غير موجود.',
        413 => 'الملف كبير جدًا أو المساحة غير كافية.',
        426 => 'يجب استخدام HTTPS لهذا الخادم.',
        429 => 'عدد المحاولات كبير؛ انتظر قليلًا.',
        _ => 'حدث خطأ في الخادم.',
      };

  @override
  String toString() => message;
}
