import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  static const _storage = FlutterSecureStorage();
  String _baseUrl = '';
  String? _token;

  Future<void> login(String server, String username, String password) async {
    final normalized = server.trim().replaceFirst(RegExp(r'/+$'), '');
    final response = await http
        .post(
          Uri.parse('$normalized/api/auth/login'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'username': username, 'password': password}),
        )
        .timeout(const Duration(seconds: 12));
    final data = _decode(response);
    _baseUrl = normalized;
    _token = data['access_token'] as String?;
    if (_token == null) throw ApiException('Token login tidak ditemukan.');
    await _storage.write(key: 'token', value: _token);
    await _storage.write(key: 'server_url', value: normalized);
  }

  Future<String?> savedServer() => _storage.read(key: 'server_url');

  Future<bool> restoreSession() async {
    _baseUrl = await _storage.read(key: 'server_url') ?? '';
    _token = await _storage.read(key: 'token');
    if (_baseUrl.isEmpty || _token == null) return false;
    try {
      await get('/api/auth/me');
      return true;
    } catch (_) {
      _token = null;
      await _storage.delete(key: 'token');
      return false;
    }
  }

  Future<Map<String, String>> _headers() async {
    _token ??= await _storage.read(key: 'token');
    if (_token == null) throw ApiException('Silakan login kembali.');
    return {'Authorization': 'Bearer ${_token!}', 'Content-Type': 'application/json'};
  }

  Future<dynamic> get(String path) async {
    final response = await http
        .get(Uri.parse('$_baseUrl$path'), headers: await _headers())
        .timeout(const Duration(seconds: 20));
    return _decode(response);
  }

  Future<dynamic> post(String path, [Map<String, dynamic>? body]) async {
    final response = await http
        .post(Uri.parse('$_baseUrl$path'), headers: await _headers(), body: jsonEncode(body ?? {}))
        .timeout(const Duration(seconds: 30));
    return _decode(response);
  }

  /// Profile VLAN dari OLT: `/api/vlans`, dengan cadangan `/api/profiles` untuk server yang belum diperbarui.
  Future<Map<String, dynamic>> vlanData() async {
    try {
      return await get('/api/vlans') as Map<String, dynamic>;
    } catch (_) {
      return await get('/api/profiles') as Map<String, dynamic>;
    }
  }

  dynamic _decode(http.Response response) {
    dynamic value;
    try {
      value = jsonDecode(response.body);
    } on FormatException {
      value = response.body;
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final message = value is Map ? value['detail'] : null;
      throw ApiException(message?.toString() ?? 'Permintaan gagal (${response.statusCode}).');
    }
    return value;
  }
}

class ApiException implements Exception {
  ApiException(this.message);
  final String message;

  @override
  String toString() => message;
}
