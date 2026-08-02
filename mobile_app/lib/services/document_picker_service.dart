import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:voice_ai_mobile/core/errors/app_exception.dart';

class DocumentPickerService {
  Future<String?> pickAny() async {
    final result = await FilePicker.platform.pickFiles(type: FileType.any, allowMultiple: false);
    return _resolve(result);
  }

  Future<String?> pick({required List<String> extensions}) async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: extensions,
      allowMultiple: false,
    );
    return _resolve(result);
  }

  Future<String?> _resolve(FilePickerResult? result) async {
    if (result == null || result.files.isEmpty) return null;
    final selected = result.files.single;
    if (selected.path != null) return selected.path;
    final bytes = selected.bytes;
    if (bytes == null) throw const AppException('تعذر قراءة الملف من مدير الملفات.');
    final cache = await getTemporaryDirectory();
    final target = File(p.join(cache.path, '${DateTime.now().microsecondsSinceEpoch}_${selected.name}'));
    await target.writeAsBytes(bytes, flush: true);
    return target.path;
  }

  Future<String?> chooseSavePath(String fileName) => FilePicker.platform.saveFile(
        dialogTitle: 'حفظ الملف الصوتي',
        fileName: fileName,
      );
}
