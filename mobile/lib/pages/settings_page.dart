import 'package:flutter/material.dart';

import '../services/api_client.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});
  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final _name = TextEditingController();
  final _ip = TextEditingController();
  final _port = TextEditingController(text: '23');
  final _username = TextEditingController();
  final _password = TextEditingController();
  List<dynamic> _profiles = [];
  bool _loading = false;

  Future<void> _loadProfiles() async {
    setState(() => _loading = true);
    try {
      final profiles = await ApiClient.instance.get('/api/olt/profiles');
      setState(() => _profiles = profiles as List<dynamic>);
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Map<String, dynamic> _formData() => {
        'name': _name.text.trim(),
        'ip': _ip.text.trim(),
        'port': int.tryParse(_port.text) ?? 23,
        'username': _username.text.trim(),
        'password': _password.text,
      };

  Future<void> _test() async {
    try {
      final result = await ApiClient.instance.post('/api/olt/test-connection', _formData());
      if (mounted) {
        final connected = result['connected'] == true;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(connected ? 'OLT terhubung.' : 'Koneksi gagal: ${result['reason']}')));
      }
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }

  Future<void> _save() async {
    try {
      await ApiClient.instance.post('/api/olt/profiles', _formData());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Profil disimpan. Password tersimpan terenkripsi di server.')));
        await _loadProfiles();
      }
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }

  Future<void> _saveConfig() async {
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Simpan konfigurasi OLT?'),
        content: const Text('Tindakan ini menulis konfigurasi aktif ke OLT. Pastikan semua perubahan benar.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Batal')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Simpan konfigurasi')),
        ],
      ),
    );
    if (accepted != true) return;
    try {
      await ApiClient.instance.post('/api/olt/save-config', {'confirm': true});
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Konfigurasi tersimpan.')));
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }

  @override
  void initState() {
    super.initState();
    _loadProfiles();
  }

  @override
  void dispose() {
    _name.dispose();
    _ip.dispose();
    _port.dispose();
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(16), children: [
        Text('Profil OLT', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        TextField(controller: _name, decoration: const InputDecoration(labelText: 'Nama profil')),
        const SizedBox(height: 10),
        TextField(controller: _ip, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'IP OLT')),
        const SizedBox(height: 10),
        TextField(controller: _port, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Port Telnet')),
        const SizedBox(height: 10),
        TextField(controller: _username, decoration: const InputDecoration(labelText: 'Username OLT')),
        const SizedBox(height: 10),
        TextField(controller: _password, obscureText: true, decoration: const InputDecoration(labelText: 'Password OLT')),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(onPressed: _test, icon: const Icon(Icons.wifi_tethering), label: const Text('Tes koneksi')),
          FilledButton.icon(onPressed: _save, icon: const Icon(Icons.save), label: const Text('Simpan profil')),
        ]),
        const SizedBox(height: 20),
        Text('Profil tersimpan', style: Theme.of(context).textTheme.titleMedium),
        if (_loading) const LinearProgressIndicator(),
        if (!_loading && _profiles.isEmpty) const Text('Belum ada profil OLT.'),
        ..._profiles.map((profile) {
          final item = profile as Map<String, dynamic>;
          return ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(item['selected'] == true ? Icons.check_circle : Icons.router),
            title: Text(item['name'].toString()),
            subtitle: Text('${item['username']}@${item['ip']}:${item['port']}'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () async {
              try {
                await ApiClient.instance.post('/api/olt/profiles/${item['id']}/select');
                await _loadProfiles();
                if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Profil ${item['name']} dipilih.')));
              } catch (error) {
                if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
              }
            },
          );
        }),
        const Divider(height: 32),
        FilledButton.tonalIcon(onPressed: _saveConfig, icon: const Icon(Icons.save_as), label: const Text('Simpan konfigurasi OLT')),
        const SizedBox(height: 10),
        const Text('Jangan gunakan jaringan HTTP publik. Gunakan HTTPS atau VPN (misalnya WireGuard/Tailscale) bila diakses dari luar LAN.'),
      ]);
}
