import 'package:flutter/material.dart';
import 'screens/app_layout.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const DawaiFlowApp());
}

class DawaiFlowApp extends StatelessWidget {
  const DawaiFlowApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'DawaiFlow Mobile',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.light,
      home: const AppLayout(),
    );
  }
}
