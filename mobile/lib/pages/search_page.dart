import 'package:flutter/material.dart';

import '../services/api_client.dart';
import 'ont_detail_page.dart';

class SearchPage extends StatefulWidget {
  const SearchPage({super.key});
  @override
  State<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends State<SearchPage> {
  final _query = TextEditingController();
  List<dynamic> _results = [];
  bool _loading = false;
  String? _error;

  Future<void> _search() async {
    if (_query.text.trim().isEmpty) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final value = await ApiClient.instance.get('/api/onts/search?q=${Uri.encodeQueryComponent(_query.text.trim())}');
      setState(() => _results = value as List<dynamic>);
    } catch (error) {
      setState(() => _error = error.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(16),
        child: Column(children: [
          TextField(
            controller: _query,
            onSubmitted: (_) => _search(),
            decoration: InputDecoration(
              labelText: 'Nama, SN, atau username PPPoE',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: IconButton(onPressed: _search, icon: const Icon(Icons.arrow_forward)),
            ),
          ),
          if (_loading) const LinearProgressIndicator(),
          if (_error != null) Padding(padding: const EdgeInsets.all(8), child: Text(_error!)),
          Expanded(
            child: _results.isEmpty
                ? Center(child: Text(_error ?? (_query.text.isEmpty ? 'Masukkan kata kunci pencarian.' : 'ONT tidak ditemukan.')))
                : ListView.builder(
                    itemCount: _results.length,
                    itemBuilder: (context, index) {
                      final ont = _results[index] as Map<String, dynamic>;
                      return Card(
                        child: ListTile(
                          title: Text((ont['name']?.toString().isNotEmpty ?? false) ? ont['name'].toString() : ont['serial'].toString()),
                          subtitle: Text('${ont['serial']} • ${ont['pppoe_user'] ?? '-'} • PON ${ont['pon']}'),
                          trailing: _StatusBadge(status: ont['status']?.toString() ?? 'offline'),
                          onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => OntDetailPage(interface: ont['interface'].toString()))),
                        ),
                      );
                    },
                  ),
          ),
        ]),
      );
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});
  final String status;
  @override
  Widget build(BuildContext context) {
    final color = switch (status) { 'online' => Colors.green, 'los' => Colors.red, _ => Colors.grey };
    return Chip(label: Text(status.toUpperCase()), backgroundColor: color.withValues(alpha: 0.15), side: BorderSide(color: color));
  }
}
