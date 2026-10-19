import 'package:flutter/material.dart';

import 'pages/splash_page.dart';

void main() => runApp(const OltControlApp());

class OltControlApp extends StatelessWidget {
  const OltControlApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'OLT Control',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff006b62)),
          inputDecorationTheme: const InputDecorationTheme(border: OutlineInputBorder()),
          cardTheme: const CardThemeData(elevation: 1),
        ),
        home: const SplashPage(),
      );
}
