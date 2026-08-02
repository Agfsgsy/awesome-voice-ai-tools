import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:voice_ai_mobile/core/providers/providers.dart';
import 'package:voice_ai_mobile/models/mobile_models.dart';
import 'package:voice_ai_mobile/widgets/responsive_page.dart';

class TrackedJobsPanel extends ConsumerWidget {
  const TrackedJobsPanel({this.onlyJobId, this.onCompleted, super.key});

  final String? onlyJobId;
  final void Function(MobileJob job)? onCompleted;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final all = ref.watch(jobControllerProvider);
    final jobs = onlyJobId == null
        ? all.values.toList()
        : <MobileJob>[if (all[onlyJobId] case final MobileJob job) job];
    if (jobs.isEmpty) return const SizedBox.shrink();
    jobs.sort((a, b) => b.id.compareTo(a.id));
    return SectionCard(
      title: 'المهام والعمليات',
      icon: Icons.pending_actions_rounded,
      child: Column(
        children: jobs.map((job) {
          if (job.status == 'completed') {
            WidgetsBinding.instance.addPostFrameCallback((_) => onCompleted?.call(job));
          }
          return Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(child: Text(job.message, style: const TextStyle(fontWeight: FontWeight.w600))),
                    Text('${job.progress}٪'),
                    if (job.canCancel)
                      IconButton(
                        tooltip: 'إلغاء المهمة',
                        onPressed: () => ref.read(jobControllerProvider.notifier).cancel(job.id),
                        icon: const Icon(Icons.cancel_outlined),
                      )
                    else if (job.finished)
                      IconButton(
                        tooltip: 'إخفاء',
                        onPressed: () => ref.read(jobControllerProvider.notifier).dismiss(job.id),
                        icon: const Icon(Icons.close),
                      ),
                  ],
                ),
                LinearProgressIndicator(value: job.finished ? 1 : job.progress / 100),
                if (job.error != null) Padding(padding: const EdgeInsets.only(top: 6), child: Text(job.error!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }
}
