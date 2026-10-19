import 'package:flutter/material.dart';

import 'dashboard_page.dart';
import 'logs_page.dart';
import 'registration_page.dart';
import 'search_page.dart';
import 'settings_page.dart';
import 'sync_page.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  int _index = 0;
  static const _pages = [
    DashboardPage(),
    SearchPage(),
    RegistrationPage(),
    SyncPage(),
    SettingsPage(),
  ];
  static const _titles = ['Dashboard', 'Cari ONT', 'Registrasi', 'Sinkronisasi', 'Pengaturan'];

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: Text(_titles[_index]),
          actions: [
            IconButton(
              tooltip: 'Log aktivitas',
              icon: const Icon(Icons.history),
              onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const LogsPage())),
            ),
          ],
        ),
        body: IndexedStack(index: _index, children: _pages),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: (index) => setState(() => _index = index),
          destinations: const [
            NavigationDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: 'Dashboard'),
            NavigationDestination(icon: Icon(Icons.search), label: 'Cari'),
            NavigationDestination(icon: Icon(Icons.add_box_outlined), selectedIcon: Icon(Icons.add_box), label: 'Registrasi'),
            NavigationDestination(icon: Icon(Icons.sync), label: 'Sync'),
            NavigationDestination(icon: Icon(Icons.settings_outlined), selectedIcon: Icon(Icons.settings), label: 'Setting'),
          ],
        ),
      );
}
