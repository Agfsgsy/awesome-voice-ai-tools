import 'dart:async';
import 'dart:io';

import 'package:multicast_dns/multicast_dns.dart';

class DiscoveredServer {
  const DiscoveredServer({required this.name, required this.url});

  final String name;
  final String url;
}

class ServerDiscoveryService {
  Future<List<DiscoveredServer>> discover({Duration timeout = const Duration(seconds: 5)}) async {
    final client = MDnsClient();
    final found = <String, DiscoveredServer>{};
    await client.start();
    try {
      final pointers = client
          .lookup<PtrResourceRecord>(ResourceRecordQuery.serverPointer('_voiceai._tcp.local'))
          .timeout(timeout, onTimeout: (sink) => sink.close());
      await for (final pointer in pointers) {
        final services = client
            .lookup<SrvResourceRecord>(ResourceRecordQuery.service(pointer.domainName))
            .timeout(const Duration(seconds: 2), onTimeout: (sink) => sink.close());
        await for (final service in services) {
          final addresses = client
              .lookup<IPAddressResourceRecord>(ResourceRecordQuery.addressIPv4(service.target))
              .timeout(const Duration(seconds: 2), onTimeout: (sink) => sink.close());
          await for (final address in addresses) {
            final host = address.address.address;
            final url = 'http://$host:${service.port}';
            found[url] = DiscoveredServer(name: pointer.domainName.replaceAll('._voiceai._tcp.local', ''), url: url);
          }
        }
      }
    } on SocketException {
      return const <DiscoveredServer>[];
    } finally {
      client.stop();
    }
    return found.values.toList();
  }
}
