import 'package:flutter/material.dart';

import '../services/api_client.dart';

class RegistrationPage extends StatefulWidget {
  const RegistrationPage({super.key});
  @override
  State<RegistrationPage> createState() => _RegistrationPageState();
}

class _RegistrationPageState extends State<RegistrationPage> {
  List<dynamic> _candidates = [];
  List<String> _profiles = [];
  List<Map<String, dynamic>> _vlanProfiles = [];
  String _vlanProfile = '';
  bool _loading = true;
  String? _error;
  Map<String, dynamic>? _selected;

  final _name = TextEditingController();
  final _vlan = TextEditingController(text: '100');
  final _pppoeUser = TextEditingController();
  final _pppoePassword = TextEditingController();
  String _profile = '';
  String _mode = 'pppoe';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([
        ApiClient.instance.get('/api/onts/unconfigured'),
        ApiClient.instance.get('/api/profiles'),
      ]);
      setState(() {
        _candidates = results[0] as List<dynamic>;
        _profiles = ((results[1] as Map<String, dynamic>)['bandwidth'] as List<dynamic>).map((e) => e.toString()).toList();
        _profile = _profiles.isEmpty ? '' : _profiles.first;
      });
      try {
        final vlanData = await ApiClient.instance.get('/api/vlans') as Map<String, dynamic>;
        setState(() => _vlanProfiles = (vlanData['vlan_profiles'] as List<dynamic>? ?? []).map((e) => Map<String, dynamic>.from(e as Map)).toList());
      } catch (_) {
        // Daftar VLAN opsional: bila gagal, VLAN diisi manual.
      }
    } catch (error) {
      setState(() => _error = error.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _register() async {
    final candidate = _selected!;
    final vlan = int.tryParse(_vlan.text);
    if (vlan == null || _name.text.trim().isEmpty || _profile.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Nama, VLAN, dan profile wajib diisi.')));
      return;
    }
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Konfirmasi registrasi'),
        content: Text('PON ${candidate['pon']}, SN ${candidate['serial']}, nama ${_name.text}, VLAN $vlan, profile $_profile, mode $_mode.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Kembali')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Daftarkan')),
        ],
      ),
    );
    if (accepted != true) return;
    try {
      final registered = await ApiClient.instance.post('/api/onts/register', {
        'pon': candidate['pon'],
        'serial': candidate['serial'],
        'name': _name.text.trim(),
        'vlan': vlan,
        'profile': _profile,
        'pppoe_user': _mode == 'bridge' ? '' : _pppoeUser.text.trim(),
        'pppoe_password': _mode == 'bridge' ? '' : _pppoePassword.text,
        'mode': _mode,
        if (_vlanProfile.isNotEmpty) 'vlan_profile': _vlanProfile,
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Registrasi berhasil.')));
      final needSave = (registered as Map<String, dynamic>)['save_config_required'] != false;
      final save = !needSave ? false : await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Simpan konfigurasi OLT?'),
          content: const Text('Simpan perubahan registrasi ke konfigurasi OLT sekarang?'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Nanti')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Simpan')),
          ],
        ),
      );
      if (save == true) {
        await ApiClient.instance.post('/api/olt/save-config', {'confirm': true});
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Konfigurasi tersimpan.')));
      }
      setState(() => _selected = null);
      await _load();
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _vlan.dispose();
    _pppoeUser.dispose();
    _pppoePassword.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return Center(child: Padding(padding: const EdgeInsets.all(24), child: Column(mainAxisSize: MainAxisSize.min, children: [Text(_error!), TextButton(onPressed: _load, child: const Text('Coba lagi'))])));
    if (_selected == null) {
      return RefreshIndicator(
        onRefresh: _load,
        child: _candidates.isEmpty
            ? ListView(children: const [SizedBox(height: 180), Center(child: Text('Tidak ada ONT belum terkonfigurasi.'))])
            : ListView(padding: const EdgeInsets.all(12), children: [
                const Text('Pilih ONT yang terdeteksi dari OLT untuk memulai registrasi.'),
                ..._candidates.map((item) {
                  final candidate = item as Map<String, dynamic>;
                  return Card(
                    child: ListTile(
                      leading: const CircleAvatar(child: Icon(Icons.fiber_new)),
                      title: Text('SN ${candidate['serial']}'),
                      subtitle: Text('PON ${candidate['pon']} • ONU ID berikutnya: ${candidate['next_onu_id'] ?? 'PON penuh'}'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => setState(() => _selected = candidate),
                    ),
                  );
                }),
              ]),
      );
    }
    final candidate = _selected!;
    return ListView(padding: const EdgeInsets.all(16), children: [
      Card(child: ListTile(title: Text('PON ${candidate['pon']} • ONU ID ${candidate['next_onu_id'] ?? '-'}'), subtitle: Text('SN ${candidate['serial']}'))),
      const SizedBox(height: 12),
      TextField(controller: _name, decoration: const InputDecoration(labelText: 'Nama pelanggan')),
      const SizedBox(height: 12),
      if (_vlanProfiles.isNotEmpty)
        DropdownButtonFormField<String>(
          initialValue: _vlanProfile.isEmpty ? null : _vlanProfile,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Profile VLAN dari OLT'),
          items: _vlanProfiles.map((v) => DropdownMenuItem(value: v['name'].toString(), child: Text('${v['name']}'))).toList(),
          onChanged: (value) => setState(() {
            _vlanProfile = value ?? '';
            final match = _vlanProfiles.where((v) => v['name'].toString() == _vlanProfile);
            if (match.isNotEmpty) _vlan.text = '${match.first['vlan']}';
          }),
        )
      else
        TextField(controller: _vlan, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'VLAN')),
      const SizedBox(height: 12),
      DropdownButtonFormField<String>(
        initialValue: _profiles.contains(_profile) ? _profile : null,
        decoration: const InputDecoration(labelText: 'Profile bandwidth'),
        items: _profiles.map((profile) => DropdownMenuItem(value: profile, child: Text(profile))).toList(),
        onChanged: (value) => setState(() => _profile = value ?? ''),
      ),
      const SizedBox(height: 12),
      SegmentedButton<String>(
        segments: const [
          ButtonSegment(value: 'pppoe', label: Text('PPPoE')),
          ButtonSegment(value: 'bridge', label: Text('Bridge')),
          ButtonSegment(value: 'hybrid', label: Text('Hybrid')),
        ],
        selected: {_mode},
        onSelectionChanged: (value) => setState(() => _mode = value.first),
      ),
      if (_mode != 'bridge') ...[
        const SizedBox(height: 12),
        TextField(controller: _pppoeUser, decoration: const InputDecoration(labelText: 'Username PPPoE')),
        const SizedBox(height: 12),
        TextField(controller: _pppoePassword, obscureText: true, decoration: const InputDecoration(labelText: 'Password PPPoE')),
      ],
      const SizedBox(height: 20),
      FilledButton.icon(onPressed: _register, icon: const Icon(Icons.check), label: const Text('Tinjau dan registrasi')),
      TextButton(onPressed: () => setState(() => _selected = null), child: const Text('Kembali ke daftar')),
    ]);
  }
}
