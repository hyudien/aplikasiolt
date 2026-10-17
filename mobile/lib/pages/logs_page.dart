import 'package:flutter/material.dart';

import '../services/api_client.dart';

class LogsPage extends StatelessWidget {
  const LogsPage({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Log Aktivitas')),
        body: FutureBuilder<dynamic>(
          future: ApiClient.instance.get('/api/logs'),
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
            if (snapshot.hasError) return Center(child: Text(snapshot.error.toString()));
            final logs = snapshot.data as List<dynamic>;
            if (logs.isEmpty) return const Center(child: Text('Belum ada aktivitas tercatat.'));
            return ListView.builder(
              itemCount: logs.length,
              itemBuilder: (context, index) {
                final item = logs[index] as Map<String, dynamic>;
                return ListTile(
                  leading: Icon(item['result'] == 'success' ? Icons.check_circle_outline : Icons.error_outline),
                  title: Text('${item['action']} • ${item['target']}'),
                  subtitle: Text('${item['username']} • ${item['created_at']}\n${item['result']} ${item['details'] ?? ''}'),
                  isThreeLine: true,
                );
              },
            );
          },
        ),
      );
}
