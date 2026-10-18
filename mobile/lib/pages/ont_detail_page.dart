import 'package:flutter/material.dart';

import '../services/api_client.dart';

class OntDetailPage extends StatefulWidget {
  const OntDetailPage({super.key, required this.interface});
  final String interface;
  @override
  State<OntDetailPage> createState() => _OntDetailPageState();
}

class _OntDetailPageState extends State<OntDetailPage> {
  bool _busy = false;

  Future<void> _action(String action, {bool confirm = false, String? field, String? label}) async {
    final values = <String, dynamic>{};
    if (action == 'change-pppoe') {
      final username = TextEditingController();
      final password = TextEditingController();
      final credentials = await showDialog<Map<String, String>>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Ubah akun PPPoE'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(controller: username, decoration: const InputDecoration(labelText: 'Username PPPoE')),
            const SizedBox(height: 12),
            TextField(controller: password, obscureText: true, decoration: const InputDecoration(labelText: 'Password PPPoE')),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Batal')),
            FilledButton(
              onPressed: () => Navigator.pop(context, {'username': username.text, 'password': password.text}),
              child: const Text('Simpan'),
            ),
          ],
        ),
      );
      username.dispose();
      password.dispose();
      if (credentials == null || credentials['username']!.trim().isEmpty || credentials['password']!.isEmpty) return;
      values.addAll(credentials);
    } else if (action == 'change-package') {
      List<String> tcont = [];
      List<String> traffic = [];
      try {
        final data = await ApiClient.instance.get('/api/profiles') as Map<String, dynamic>;
        tcont = (data['bandwidth'] as List<dynamic>? ?? []).map((e) => e.toString()).toList();
        traffic = (data['traffic'] as List<dynamic>? ?? []).map((e) => e.toString()).toList();
      } catch (_) {}
      if (!mounted) return;
      final manual = TextEditingController();
      String? selTcont, selUp, selDown;
      Widget picker(String label, List<String> items, String? value, void Function(String?) onChanged) =>
          DropdownButtonFormField<String>(
            initialValue: value,
            isExpanded: true,
            decoration: InputDecoration(labelText: label),
            items: items.map((p) => DropdownMenuItem(value: p, child: Text(p))).toList(),
            onChanged: onChanged,
          );
      final chosen = await showDialog<Map<String, String>>(
        context: context,
        builder: (context) => StatefulBuilder(
          builder: (context, setLocal) => AlertDialog(
            title: const Text('Ubah paket'),
            content: SingleChildScrollView(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                if (tcont.isEmpty)
                  TextField(controller: manual, decoration: const InputDecoration(labelText: 'T-CONT profile (daftar OLT tidak tersedia)'))
                else
                  picker('T-CONT profile', tcont, selTcont, (v) => setLocal(() => selTcont = v)),
                if (traffic.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  picker('GEM port upstream', traffic, selUp, (v) => setLocal(() => selUp = v)),
                  const SizedBox(height: 12),
                  picker('GEM port downstream', traffic, selDown, (v) => setLocal(() => selDown = v)),
                ],
              ]),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(context), child: const Text('Batal')),
              FilledButton(
                onPressed: () => Navigator.pop(context, {
                  'profile': tcont.isEmpty ? manual.text : (selTcont ?? ''),
                  'upstream': selUp ?? '',
                  'downstream': selDown ?? '',
                }),
                child: const Text('Lanjut'),
              ),
            ],
          ),
        ),
      );
      manual.dispose();
      if (chosen == null || chosen['profile']!.trim().isEmpty) return;
      if ((chosen['upstream']!.isEmpty) != (chosen['downstream']!.isEmpty)) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Pilih upstream dan downstream bersamaan.')));
        }
        return;
      }
      values['profile'] = chosen['profile']!.trim();
      if (chosen['upstream']!.isNotEmpty) {
        values['upstream'] = chosen['upstream'];
        values['downstream'] = chosen['downstream'];
      }
    } else if (field != null) {
      final controller = TextEditingController();
      final value = await showDialog<String>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(label ?? 'Masukkan nilai'),
          content: TextField(controller: controller, autofocus: true, decoration: InputDecoration(labelText: label)),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Batal')),
            FilledButton(onPressed: () => Navigator.pop(context, controller.text), child: const Text('Lanjut')),
          ],
        ),
      );
      controller.dispose();
      if (value == null || value.trim().isEmpty) return;
      values[field] = field == 'vlan' ? int.tryParse(value) : value.trim();
    }
    if (confirm) {
      if (!mounted) return;
      final accepted = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Konfirmasi aksi'),
          content: Text('Yakin menjalankan aksi $action untuk ONT ${widget.interface}?'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Batal')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Konfirmasi')),
          ],
        ),
      );
      if (accepted != true) return;
      values['confirm'] = true;
    }
    setState(() => _busy = true);
    try {
      final result = await ApiClient.instance.post('/api/onts/${widget.interface}/actions/$action', values);
      if (mounted) {
        final message = result['optical_power'] == null
            ? (result['message']?.toString() ?? 'Aksi berhasil.')
            : 'Daya optik: ${result['optical_power']}';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
        setState(() {});
      }
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _refresh() async {
    setState(() => _busy = true);
    try {
      await ApiClient.instance.post('/api/onts/${widget.interface}/refresh');
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Data ONT diperbarui dari OLT.')));
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Detail ONT')),
        body: FutureBuilder<dynamic>(
          future: ApiClient.instance.get('/api/onts/${widget.interface}'),
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
            if (snapshot.hasError) return Center(child: Text(snapshot.error.toString()));
            final ont = snapshot.data as Map<String, dynamic>;
            return ListView(padding: const EdgeInsets.all(16), children: [
              Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(ont['name']?.toString().isNotEmpty == true ? ont['name'].toString() : ont['serial'].toString(), style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 12),
                _info('SN', ont['serial']), _info('PON / ONU ID', '${ont['pon']} / ${ont['onu_id']}'),
                _info('Status', '${ont['status']} (${ont['reason'] ?? '-'})'),
                _info('PPPoE', ont['pppoe_user'] ?? '-'), _info('VLAN / Paket', '${ont['vlan'] ?? '-'} / ${ont['profile'] ?? '-'}'),
                _info('Mode', ont['mode'] ?? '-'), _info('Daya optik', ont['optical_power'] ?? 'Belum tersedia'),
              ]))),
              if (_busy) const LinearProgressIndicator(),
              const SizedBox(height: 8),
              FilledButton.icon(onPressed: _busy ? null : _refresh, icon: const Icon(Icons.refresh), label: const Text('Perbarui data')),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: [
                _button('Cek redaman', Icons.bolt, () => _action('attenuation')),
                _button('Ubah paket', Icons.speed, () => _action('change-package', field: 'profile', label: 'Profile bandwidth')),
                _button('Ubah VLAN', Icons.lan, () => _action('change-vlan', field: 'vlan', label: 'VLAN')),
                _button('Ubah PPPoE', Icons.person, () => _action('change-pppoe')),
                _button('Ganti ONT', Icons.swap_horiz, () => _action('replace', confirm: true, field: 'serial', label: 'SN ONT baru')),
                _button('Enable remote', Icons.settings_remote, () => _action('remote-on')),
                _button('Disable remote', Icons.portable_wifi_off, () => _action('remote-off')),
                _button('Reboot', Icons.restart_alt, () => _action('reboot', confirm: true)),
                _button('Delete', Icons.delete_outline, () => _action('delete', confirm: true), danger: true),
              ]),
            ]);
          },
        ),
      );

  Widget _info(String label, Object? value) => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Row(children: [SizedBox(width: 130, child: Text(label)), Expanded(child: Text('$value', style: const TextStyle(fontWeight: FontWeight.w600)))]),
      );

  Widget _button(String label, IconData icon, VoidCallback action, {bool danger = false}) => FilledButton.tonalIcon(
        onPressed: _busy ? null : action,
        icon: Icon(icon),
        label: Text(label),
        style: danger ? FilledButton.styleFrom(foregroundColor: Theme.of(context).colorScheme.error) : null,
      );
}
