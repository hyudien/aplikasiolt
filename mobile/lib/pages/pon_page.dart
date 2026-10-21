import 'package:flutter/material.dart';

import '../services/api_client.dart';
import 'ont_detail_page.dart';

class PonPage extends StatefulWidget {
  const PonPage({super.key, required this.pon});
  final String pon;
  @override
  State<PonPage> createState() => _PonPageState();
}

class _PonPageState extends State<PonPage> {
  Map<int, String> _vlanNames = {};

  @override
  void initState() {
    super.initState();
    ApiClient.instance.vlanNames().then((names) {
      if (mounted) setState(() => _vlanNames = names);
    });
  }

  String _vlanLabel(dynamic vlan) {
    final number = int.tryParse('$vlan');
    if (number == null) return '-';
    final name = _vlanNames[number];
    return name == null ? '$number' : name;
  }

  String _filter = 'Semua';
  String _query = '';

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text('PON ${widget.pon}')),
        body: FutureBuilder<dynamic>(
          future: ApiClient.instance.get('/api/olt/pons/${widget.pon}'),
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
            if (snapshot.hasError) return Center(child: Text(snapshot.error.toString()));
            final all = (snapshot.data['onts'] as List<dynamic>? ?? []);
            final filtered = all.where((item) {
              final ont = item as Map<String, dynamic>;
              final status = ont['status']?.toString() ?? 'offline';
              final filterMatch = _filter == 'Semua' || (_filter == 'Online' && status == 'online') ||
                  (_filter == 'Offline' && status == 'offline') || (_filter == 'LOS' && status == 'los');
              final text = '${ont['name']} ${ont['serial']} ${ont['pppoe_user']} ${ont['profile']} ${ont['vlan']}'.toLowerCase();
              return filterMatch && text.contains(_query.toLowerCase());
            }).toList();
            return Column(children: [
              Padding(
                padding: const EdgeInsets.all(12),
                child: Column(children: [
                  TextField(onChanged: (value) => setState(() => _query = value), decoration: const InputDecoration(prefixIcon: Icon(Icons.search), labelText: 'Cari di PON ini')),
                  const SizedBox(height: 8),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(children: ['Semua', 'Online', 'Offline', 'LOS'].map((label) => Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(label: Text(label), selected: _filter == label, onSelected: (_) => setState(() => _filter = label)),
                    )).toList()),
                  ),
                ]),
              ),
              Expanded(
                child: filtered.isEmpty
                    ? const Center(child: Text('Tidak ada ONT untuk filter ini.'))
                    : ListView.builder(
                        itemCount: filtered.length,
                        itemBuilder: (context, index) {
                          final ont = filtered[index] as Map<String, dynamic>;
                          return ListTile(
                            leading: CircleAvatar(child: Text('${ont['onu_id'] ?? '-'}')),
                            title: Text((ont['name']?.toString().isNotEmpty ?? false) ? ont['name'].toString() : ont['serial'].toString()),
                            subtitle: Text('${ont['serial']} • ${ont['reason'] ?? ont['status']}\nPaket: ${(ont['profile']?.toString().isNotEmpty ?? false) ? ont['profile'] : '-'} • VLAN: ${_vlanLabel(ont['vlan'])} • PPPoE: ${(ont['pppoe_user']?.toString().isNotEmpty ?? false) ? ont['pppoe_user'] : '-'}'),
                            isThreeLine: true,
                            trailing: Text(ont['status'].toString().toUpperCase()),
                            onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => OntDetailPage(interface: ont['interface'].toString()))),
                          );
                        },
                      ),
              ),
            ]);
          },
        ),
      );
}
