import 'package:flutter/material.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';

class AudioAnalysisCard extends StatelessWidget {
  const AudioAnalysisCard({required this.analysis, super.key});

  final AudioAnalysis analysis;

  @override
  Widget build(BuildContext context) {
    final values = <(String, String, IconData)>[
      ('المدة', '${analysis.durationSeconds.toStringAsFixed(1)} ث', Icons.timer_outlined),
      ('الضوضاء', '${analysis.noiseFloorDbfs.toStringAsFixed(1)} dBFS', Icons.noise_aware_rounded),
      ('الصمت', '${analysis.silencePercent.toStringAsFixed(1)}٪', Icons.volume_off_rounded),
      ('التشويه', '${analysis.distortion} (${analysis.clippingPercent.toStringAsFixed(2)}٪)', Icons.warning_amber_rounded),
      ('العينة', '${analysis.sampleQuality} – ${analysis.sampleRate} Hz', Icons.high_quality_rounded),
    ];
    return SectionCard(
      title: 'تحليل جودة التسجيل',
      icon: Icons.analytics_rounded,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              SizedBox(
                width: 68,
                height: 68,
                child: Stack(
                  alignment: Alignment.center,
                  children: <Widget>[
                    CircularProgressIndicator(value: analysis.qualityScore / 100, strokeWidth: 7),
                    Text('${analysis.qualityScore}', style: const TextStyle(fontWeight: FontWeight.bold)),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(analysis.clearSpeech ? 'الكلام واضح' : 'يحتاج إلى إعادة تسجيل', style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 4),
                    Text(analysis.recommendation),
                  ],
                ),
              ),
            ],
          ),
          const Divider(height: 28),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: values
                .map(
                  (value) => SizedBox(
                    width: 190,
                    child: ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(value.$3),
                      title: Text(value.$1),
                      subtitle: Text(value.$2),
                    ),
                  ),
                )
                .toList(),
          ),
          if (analysis.issues.isNotEmpty)
            ...analysis.issues.map(
              (issue) => Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Row(children: <Widget>[const Icon(Icons.info_outline, size: 18, color: Colors.orange), const SizedBox(width: 6), Expanded(child: Text(issue))]),
              ),
            ),
        ],
      ),
    );
  }
}
