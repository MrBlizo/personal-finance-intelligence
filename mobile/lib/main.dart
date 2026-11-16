import 'package:cryptography_flutter/cryptography_flutter.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'data/db.dart';
import 'data/schema.dart';
import 'state.dart';
import 'ui/settings.dart';
import 'ui/shell.dart';
import 'ui/theme.dart';
import 'ui/widgets.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  FlutterCryptography.enable();
  await initializeDateFormatting();
  final sql = await rootBundle.loadString('assets/db/schema.sql');
  final meta = SchemaMeta.parse(await rootBundle.loadString('assets/db/schema.json'));
  final dir = await getApplicationDocumentsDirectory();
  final db = AppDatabase.open(p.join(dir.path, 'pfi.sqlite'), sql, meta);
  final prefs = await SharedPreferences.getInstance();
  final state = AppState(db, prefs);
  runApp(ChangeNotifierProvider.value(value: state, child: const PfiApp()));
  if (state.syncEnabled) state.syncNow();
}

class PfiApp extends StatelessWidget {
  const PfiApp({super.key});

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    return MaterialApp(
      title: 'PFI',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(app.accent, Brightness.light),
      darkTheme: buildTheme(app.accent, Brightness.dark),
      themeMode: app.themeMode,
      locale: Locale(app.lang),
      supportedLocales: const [Locale('en'), Locale('fr'), Locale('ar')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: app.onboarded ? const HomeShell() : const WelcomePage(),
    );
  }
}

class WelcomePage extends StatefulWidget {
  const WelcomePage({super.key});
  @override
  State<WelcomePage> createState() => _WelcomePageState();
}

class _WelcomePageState extends State<WelcomePage> {
  String currency = 'CHF';

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const Spacer(),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(18),
                child: Image.asset('assets/branding/icon.png', width: 76, height: 76),
              ),
            ),
            const SizedBox(height: 24),
            Text(app.t('Welcome to PFI'),
                style: Theme.of(context).textTheme.headlineLarge),
            const SizedBox(height: 8),
            Text(app.t('Your budget, investments and plans — private, on your devices.'),
                style: Theme.of(context).textTheme.titleMedium),
            const Spacer(),
            FilledButton.icon(
              icon: const Icon(Icons.computer_outlined),
              label: Text(app.t('Connect to PFI on my PC')),
              onPressed: () => Navigator.of(context)
                  .push(MaterialPageRoute(builder: (_) => const SyncSetupPage())),
            ),
            const SizedBox(height: 12),
            Text(app.t('Choose your main currency')),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  value: currency,
                  items: [for (final c in currencies) DropdownMenuItem(value: c, child: Text(c))],
                  onChanged: (v) => setState(() => currency = v ?? currency),
                ),
              ),
              const SizedBox(width: 12),
              FilledButton.tonal(
                onPressed: () => app.finishOnboarding(currency: currency),
                child: Text(app.t('Start fresh on this phone')),
              ),
            ]),
          ]),
        ),
      ),
    );
  }
}
