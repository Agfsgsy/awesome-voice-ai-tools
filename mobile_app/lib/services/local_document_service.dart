import 'dart:io';

import 'package:docx_to_text/docx_to_text.dart';
import 'package:path/path.dart' as p;
import 'package:pdfrx/pdfrx.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';

class LocalDocumentService {
  Future<String> extractText(String path) async {
    final file = File(path);
    if (!await file.exists()) {
      throw const AppException('المستند المحدد غير موجود.');
    }
    final extension = p.extension(path).toLowerCase();
    try {
      final text = switch (extension) {
        '.txt' => await file.readAsString(),
        '.docx' => docxToText(await file.readAsBytes()),
        '.pdf' => await _extractPdf(path),
        _ => throw const AppException('صيغة المستند غير مدعومة محليًا.'),
      };
      final cleaned = text.replaceAll('\u0000', '').trim();
      if (cleaned.isEmpty) {
        throw const AppException(
          'لم يُعثر على نص قابل للقراءة داخل المستند. قد يكون PDF عبارة عن صور ممسوحة.',
        );
      }
      return cleaned;
    } on AppException {
      rethrow;
    } on Object {
      throw const AppException(
        'تعذر فك المستند. تأكد أن الملف غير تالف وغير محمي بكلمة مرور.',
      );
    }
  }

  Future<String> _extractPdf(String path) async {
    final document = await PdfDocument.openFile(path);
    try {
      final output = StringBuffer();
      for (final page in document.pages) {
        final text = await page.loadText();
        if (text != null && text.fullText.trim().isNotEmpty) {
          if (output.isNotEmpty) output.writeln();
          output.write(text.fullText);
        }
      }
      return output.toString();
    } finally {
      await document.dispose();
    }
  }
}
