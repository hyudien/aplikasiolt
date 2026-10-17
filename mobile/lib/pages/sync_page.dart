import 'package:flutter/material.dart';

import '../services/api_client.dart';

class SyncPage extends StatefulWidget {
  const SyncPage({super.key});
  @override
  State<SyncPage> createState() => _SyncPageState();
}

class _SyncPageState extends State<SyncPage> {
  final _pon = TextEditingController();
  bool _busy = false;
  List<dynamic> _jobs = [];
  String? _error;

  Future<void> _refresh() async {
    try {
      final result = await ApiClient.instance.get('/api/sync/status');
      setState(() {
        _jobs = result as List<dynamic>;
        _error = null;
      });
    } catch (error) {
      setState(() => _error = error.toString());
    }
  }

  Future<void> _sync(String scope) async {
    setState(() => _busy = true);
    try {
      await ApiClient.instance.post('/api/sync?scope=${Uri.encodeComponent(scope)}');
      await _refresh();
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Sinkronisasi selesai.')));
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  @override
  void dispose() {
    _pon.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(16), children: [
        const Text('Salin status ONT terkini dari OLT ke database lokal untuk pencarian cepat.'),
        const SizedBox(height: 16),
        FilledButton.icon(onPressed: _busy ? null : () => _sync('full'), icon: const Icon(Icons.sync), label: const Text('Sinkronisasi penuh')),
        const SizedBox(height: 12),
        TextField(controller: _pon, decoration: const InputDecoration(labelText: 'Sinkronkan PON tertentu (contoh 1/1/1)')),
        const SizedBox(height: 8),
        OutlinedButton.icon(onPressed: _busy ? null : () => _sync(_pon.text.trim()), icon: const Icon(Icons.hub), label: const Text('Sinkronkan PON')),
        if (_busy) const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: LinearProgressIndicator()),
        const SizedBox(height: 24),
        Text('Riwayat sync', style: Theme.of(context).textTheme.titleLarge),
        if (_error != null) Text(_error!),
        if (_jobs.isEmpty && _error == null) const Text('Belum ada riwayat sinkronisasi.'),
        ..._jobs.map((job) {
          final item = job as Map<String, dynamic>;
          return ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(item['status'] == 'success' ? Icons.check_circle : Icons.sync, color: item['status'] == 'success' ? Colors.green : null),
            title: Text('${item['type']} • ${item['status']}'),
            subtitle: Text('${item['started_at']} ${item['summary'] ?? ''}'),
          );
        }),
      ]);
}
