import 'package:flutter/material.dart';

import '../services/api_client.dart';
import 'home_page.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _server = TextEditingController(text: 'http://192.168.1.10:8000');
  final _username = TextEditingController(text: 'admin');
  final _password = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    ApiClient.instance.savedServer().then((value) {
      if (mounted && value != null) _server.text = value;
    });
  }

  Future<void> _login() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ApiClient.instance.login(_server.text, _username.text, _password.text);
      if (mounted) {
        Navigator.of(context).pushReplacement(MaterialPageRoute<void>(builder: (_) => const HomePage()));
      }
    } catch (error) {
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _server.dispose();
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.router, size: 72),
                  const SizedBox(height: 12),
                  Text('OLT Control', textAlign: TextAlign.center, style: Theme.of(context).textTheme.headlineMedium),
                  const SizedBox(height: 28),
                  TextField(controller: _server, keyboardType: TextInputType.url, decoration: const InputDecoration(labelText: 'Alamat server backend')),
                  const SizedBox(height: 12),
                  TextField(controller: _username, decoration: const InputDecoration(labelText: 'Username')),
                  const SizedBox(height: 12),
                  TextField(controller: _password, obscureText: true, decoration: const InputDecoration(labelText: 'Password')),
                  if (_error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
                  const SizedBox(height: 18),
                  FilledButton.icon(
                    onPressed: _loading ? null : _login,
                    icon: _loading ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.login),
                    label: Text(_loading ? 'Menghubungkan…' : 'Masuk'),
                  ),
                  const SizedBox(height: 10),
                  const Text('Untuk demo mock: admin / admin. Ganti kredensial sebelum pemakaian produksi.', textAlign: TextAlign.center),
                ],
              ),
            ),
          ),
        ),
      );
}
