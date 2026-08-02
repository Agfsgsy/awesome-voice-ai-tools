import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';

class ProjectService {
  Future<File> _indexFile() async {
    final root = await getApplicationDocumentsDirectory();
    final directory = Directory(p.join(root.path, 'projects'));
    await directory.create(recursive: true);
    return File(p.join(directory.path, 'projects.json'));
  }

  Future<List<SavedProject>> list() async {
    final file = await _indexFile();
    if (!await file.exists()) return const <SavedProject>[];
    try {
      final decoded = jsonDecode(await file.readAsString()) as List<dynamic>;
      return decoded.map((Object? value) => SavedProject.fromJson(value as Map<String, dynamic>)).toList();
    } on Object {
      return const <SavedProject>[];
    }
  }

  Future<SavedProject> create(String name) async {
    final projects = await list();
    final project = SavedProject(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      name: name.trim(),
      createdAt: DateTime.now().toUtc(),
      filePaths: const <String>[],
    );
    await _save(<SavedProject>[project, ...projects]);
    return project;
  }

  Future<void> addFile(String projectId, String sourcePath) async {
    final projects = await list();
    final root = await getApplicationDocumentsDirectory();
    final projectDirectory = Directory(p.join(root.path, 'projects', projectId));
    await projectDirectory.create(recursive: true);
    final destination = p.join(projectDirectory.path, p.basename(sourcePath));
    await File(sourcePath).copy(destination);
    await _save(
      projects
          .map(
            (project) => project.id == projectId
                ? SavedProject(
                    id: project.id,
                    name: project.name,
                    createdAt: project.createdAt,
                    filePaths: <String>{...project.filePaths, destination}.toList(),
                  )
                : project,
          )
          .toList(),
    );
  }

  Future<void> delete(String projectId) async {
    final projects = await list();
    final root = await getApplicationDocumentsDirectory();
    final directory = Directory(p.join(root.path, 'projects', projectId));
    if (await directory.exists()) await directory.delete(recursive: true);
    await _save(projects.where((project) => project.id != projectId).toList());
  }

  Future<void> _save(List<SavedProject> projects) async {
    final file = await _indexFile();
    final temporary = File('${file.path}.tmp');
    await temporary.writeAsString(jsonEncode(projects.map((project) => project.toJson()).toList()), flush: true);
    if (await file.exists()) await file.delete();
    await temporary.rename(file.path);
  }
}
