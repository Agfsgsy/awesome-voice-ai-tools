class EngineInfo {
  const EngineInfo({
    required this.name,
    required this.label,
    required this.ready,
    required this.downloading,
    required this.external,
    required this.models,
    this.error,
  });

  final String name;
  final String label;
  final bool ready;
  final bool downloading;
  final bool external;
  final List<String> models;
  final String? error;

  factory EngineInfo.fromJson(Map<String, dynamic> json) => EngineInfo(
        name: json['name'] as String? ?? 'unknown',
        label: json['label'] as String? ?? json['name'] as String? ?? 'محرك غير معروف',
        ready: json['ready'] as bool? ?? json['available'] as bool? ?? false,
        downloading: json['downloading'] as bool? ?? false,
        external: json['external'] as bool? ?? false,
        models: (json['models'] as List<dynamic>? ?? const <dynamic>[]).map((Object? value) {
          if (value is Map<String, dynamic>) {
            return (value['name'] ?? value['model_name'] ?? 'نموذج').toString();
          }
          return value.toString();
        }).toList(),
        error: json['error'] as String?,
      );
}

class MobileFileInfo {
  const MobileFileInfo({
    required this.id,
    required this.name,
    required this.size,
    required this.modifiedAt,
    required this.mimeType,
    required this.scope,
  });

  final String id;
  final String name;
  final int size;
  final DateTime modifiedAt;
  final String mimeType;
  final String scope;

  bool get isAudio => mimeType.startsWith('audio/') || RegExp(r'\.(wav|mp3|m4a|aac|flac|ogg|opus|webm)$', caseSensitive: false).hasMatch(name);

  factory MobileFileInfo.fromJson(Map<String, dynamic> json) => MobileFileInfo(
        id: json['file_id'] as String,
        name: json['name'] as String,
        size: (json['size'] as num).toInt(),
        modifiedAt: DateTime.parse(json['modified_at'] as String),
        mimeType: json['mime_type'] as String? ?? 'application/octet-stream',
        scope: json['scope'] as String? ?? 'output',
      );
}

class AudioAnalysis {
  const AudioAnalysis({
    required this.durationSeconds,
    required this.noiseFloorDbfs,
    required this.silencePercent,
    required this.clippingPercent,
    required this.sampleRate,
    required this.sampleQuality,
    required this.distortion,
    required this.qualityScore,
    required this.clearSpeech,
    required this.issues,
    required this.recommendation,
  });

  final double durationSeconds;
  final double noiseFloorDbfs;
  final double silencePercent;
  final double clippingPercent;
  final int sampleRate;
  final String sampleQuality;
  final String distortion;
  final int qualityScore;
  final bool clearSpeech;
  final List<String> issues;
  final String recommendation;

  factory AudioAnalysis.fromJson(Map<String, dynamic> json) => AudioAnalysis(
        durationSeconds: (json['duration_seconds'] as num? ?? 0).toDouble(),
        noiseFloorDbfs: (json['noise_floor_dbfs'] as num? ?? -90).toDouble(),
        silencePercent: (json['silence_percent'] as num? ?? 0).toDouble(),
        clippingPercent: (json['clipping_percent'] as num? ?? 0).toDouble(),
        sampleRate: (json['sample_rate'] as num? ?? 0).toInt(),
        sampleQuality: json['sample_quality'] as String? ?? 'غير معروفة',
        distortion: json['distortion'] as String? ?? 'غير معروف',
        qualityScore: (json['quality_score'] as num? ?? 0).toInt(),
        clearSpeech: json['clear_speech'] as bool? ?? false,
        issues: (json['issues'] as List<dynamic>? ?? const <dynamic>[]).map((Object? item) => item.toString()).toList(),
        recommendation: json['recommendation'] as String? ?? '',
      );
}

class MobileJob {
  const MobileJob({
    required this.id,
    required this.kind,
    required this.status,
    required this.progress,
    required this.message,
    required this.canCancel,
    this.result,
    this.error,
  });

  final String id;
  final String kind;
  final String status;
  final int progress;
  final String message;
  final bool canCancel;
  final Map<String, dynamic>? result;
  final String? error;

  bool get finished => const {'completed', 'failed', 'cancelled'}.contains(status);

  factory MobileJob.fromJson(Map<String, dynamic> json) => MobileJob(
        id: json['job_id'] as String,
        kind: json['kind'] as String? ?? 'operation',
        status: json['status'] as String? ?? 'queued',
        progress: (json['progress'] as num? ?? 0).toInt(),
        message: json['message'] as String? ?? 'جارٍ التنفيذ',
        canCancel: json['can_cancel'] as bool? ?? false,
        result: json['result'] is Map<String, dynamic> ? json['result'] as Map<String, dynamic> : null,
        error: json['error'] as String?,
      );
}

class SelectedReference {
  const SelectedReference({required this.localPath, required this.fileId, required this.analysis});

  final String localPath;
  final String fileId;
  final AudioAnalysis analysis;
}

class SavedProject {
  const SavedProject({required this.id, required this.name, required this.createdAt, required this.filePaths});

  final String id;
  final String name;
  final DateTime createdAt;
  final List<String> filePaths;

  factory SavedProject.fromJson(Map<String, dynamic> json) => SavedProject(
        id: json['id'] as String,
        name: json['name'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
        filePaths: (json['file_paths'] as List<dynamic>? ?? const <dynamic>[]).cast<String>(),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'created_at': createdAt.toUtc().toIso8601String(),
        'file_paths': filePaths,
      };
}
