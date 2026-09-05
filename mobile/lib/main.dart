import 'package:flutter/material.dart';
import 'app_theme.dart';
import 'screens/home_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const LuckyDoctorApp());
}

class LuckyDoctorApp extends StatelessWidget {
  const LuckyDoctorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '幸运医生',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(Brightness.light),
      darkTheme: buildAppTheme(Brightness.dark),
      home: const HomeScreen(),
    );
  }
}
