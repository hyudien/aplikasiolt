import 'package:flutter/material.dart';

import '../services/api_client.dart';
import 'pon_page.dart';

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});
  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  bool _syncing = false;

  Future<dynamic> _load() => ApiClient.instance.get('/api/olt/dashboard');

  Future<void> _refreshFromOlt() async {
    setState(() => _syncing = true);
    try {
      await ApiClient.instance.post('/api/sync?scope=full');
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Status ONT diperbarui dari OLT.')));
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
    } finally {
      if (mounted) setState(() => _syncing = false);
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<dynamic>(
        future: _load(),
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snapshot.hasError) return _ErrorState(message: snapshot.error.toString(), retry: () => setState(() {}));
          final data = snapshot.data as Map<String, dynamic>;
          final pons = (data['pons'] as List<dynamic>? ?? []);
          return RefreshIndicator(
            onRefresh: () async => setState(() {}),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Align(
                  alignment: Alignment.centerRight,
                  child: FilledButton.icon(
                    onPressed: _syncing ? null : _refreshFromOlt,
                    icon: _syncing
                        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.refresh),
                    label: Text(_syncing ? 'Memperbarui...' : 'Refresh dari OLT'),
                  ),
                ),
                const SizedBox(height: 12),
                Wrap(spacing: 10, runSpacing: 10, children: [
                  _SummaryCard(label: 'Total ONT', value: data['total'] ?? 0, icon: Icons.router),
                  _SummaryCard(label: 'Online', value: data['online'] ?? 0, icon: Icons.check_circle, color: Colors.green),
                  _SummaryCard(label: 'Offline', value: data['offline'] ?? 0, icon: Icons.cancel, color: Colors.grey),
                  _SummaryCard(label: 'LOS', value: data['los'] ?? 0, icon: Icons.warning, color: Colors.red),
                ]),
                const Padding(padding: EdgeInsets.only(top: 24, bottom: 8), child: Text('Port PON', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold))),
                if (pons.isEmpty) const _Empty(message: 'Belum ada PON. Jalankan sinkronisasi terlebih dahulu.'),
                ...pons.map((item) {
                  final pon = item as Map<String, dynamic>;
                  return Card(
                    child: ListTile(
                      leading: const CircleAvatar(child: Icon(Icons.hub_outlined)),
                      title: Text('PON ${pon['pon']}'),
                      subtitle: Text('${pon['total']} ONT • ${pon['online']} online • ${pon['los']} LOS'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => PonPage(pon: pon['pon'].toString()))),
                    ),
                  );
                }),
              ],
            ),
          );
        },
      );
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.label, required this.value, required this.icon, this.color});
  final String label;
  final Object value;
  final IconData icon;
  final Color? color;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: (MediaQuery.sizeOf(context).width - 42) / 2,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(icon, color: color),
              const SizedBox(height: 8),
              Text('$value', style: Theme.of(context).textTheme.headlineMedium),
              Text(label),
            ]),
          ),
        ),
      );
}

class _Empty extends StatelessWidget {
  const _Empty({required this.message});
  final String message;
  @override
  Widget build(BuildContext context) => Padding(padding: const EdgeInsets.all(24), child: Text(message, textAlign: TextAlign.center));
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message, required this.retry});
  final String message;
  final VoidCallback retry;
  @override
  Widget build(BuildContext context) => Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text(message, textAlign: TextAlign.center),
        const SizedBox(height: 12),
        OutlinedButton.icon(onPressed: retry, icon: const Icon(Icons.refresh), label: const Text('Coba lagi')),
      ]));
}
