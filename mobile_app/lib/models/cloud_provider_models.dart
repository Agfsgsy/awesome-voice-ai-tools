class CloudProviderConfig {
  const CloudProviderConfig({
    required this.geminiApiKey,
    required this.geminiModel,
    required this.geminiVoice,
    this.geminiTextModel = 'gemini-3.6-flash',
    required this.elevenLabsApiKey,
    required this.elevenLabsModel,
    this.elevenLabsStsModel = 'eleven_multilingual_sts_v2',
  });

  final String geminiApiKey;
  final String geminiModel;
  final String geminiVoice;
  final String geminiTextModel;
  final String elevenLabsApiKey;
  final String elevenLabsModel;
  final String elevenLabsStsModel;

  bool get hasGemini => geminiApiKey.trim().isNotEmpty;
  bool get hasElevenLabs => elevenLabsApiKey.trim().isNotEmpty;
  bool get hasAnyProvider => hasGemini || hasElevenLabs;
}

class CloudProviderStatus {
  const CloudProviderStatus({
    required this.provider,
    required this.configured,
    required this.available,
    required this.message,
    this.plan,
    this.remainingCharacters,
    this.canCloneVoice,
    this.capabilities = const <String>[],
    this.verifiedByGeneration = false,
  });

  final String provider;
  final bool configured;
  final bool available;
  final String message;
  final String? plan;
  final int? remainingCharacters;
  final bool? canCloneVoice;
  final List<String> capabilities;
  final bool verifiedByGeneration;
}

class CloudVoice {
  const CloudVoice({
    required this.id,
    required this.name,
    required this.category,
    this.description,
    this.previewUrl,
  });

  final String id;
  final String name;
  final String category;
  final String? description;
  final String? previewUrl;

  factory CloudVoice.fromElevenLabs(Map<String, dynamic> json) => CloudVoice(
        id: json['voice_id'] as String? ?? '',
        name: json['name'] as String? ?? 'صوت دون اسم',
        category: json['category'] as String? ?? 'voice',
        description: json['description'] as String?,
        previewUrl: json['preview_url'] as String?,
      );
}
