// Settings: look, language, currency and sync with PFI on the PC.
import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat;
import 'package:url_launcher/url_launcher.dart';

import '../config.dart';
import '../notify.dart';
import '../state.dart';
import '../sync/cloud.dart';
import '../updates.dart';
import 'shell.dart' show currencies;
import 'theme.dart';
import 'widgets.dart';

class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final scheme = Theme.of(context).colorScheme;
    final last = app.lastSync;
    return Scaffold(
      appBar: AppBar(title: Text(app.t('Settings'))),
      body: ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 32), children: [
        SectionTitle(app.t('Sync')),
        Card(
          child: Column(children: [
            ListTile(
              leading: Icon(app.syncEnabled ? Icons.cloud_done_outlined : Icons.cloud_outlined,
                  color: scheme.primary),
              title: Text(app.t('Sync with PFI on your PC')),
              subtitle: Text(app.syncEnabled
                  ? '${app.provider!.title} · ${app.t('Last sync: {w}', {'w': _when(last['at'], app.lang)})}'
                  : app.t('Not set up')),
            ),
            if (app.syncMessage != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(app.syncMessage!, style: TextStyle(color: scheme.error)),
              ),
            if (app.syncEnabled && app.otherDevices.isNotEmpty)
              ListTile(
                dense: true,
                title: Text(app.t('Other devices')),
                subtitle: Text(app.otherDevices
                    .map((d) => '${d['name']} (${_when(d['seen'], app.lang)})')
                    .join(' · ')),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              child: Wrap(spacing: 8, children: [
                if (app.syncEnabled) ...[
                  FilledButton.tonalIcon(
                    onPressed: app.syncing
                        ? null
                        : () async {
                            final r = await app.syncNow();
                            if (r != null && context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                                  content: Text(app.t('Synced: {s} sent, {r} received.',
                                      {'s': r.sent, 'r': r.received}))));
                            }
                          },
                    icon: const Icon(Icons.sync),
                    label: Text(app.t(app.syncing ? 'Syncing…' : 'Sync now')),
                  ),
                  TextButton(onPressed: () => app.stopSync(), child: Text(app.t('Stop syncing'))),
                ] else
                  FilledButton.icon(
                    onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => const SyncSetupPage())),
                    icon: const Icon(Icons.add_link),
                    label: Text(app.t('Set up sync')),
                  ),
              ]),
            ),
          ]),
        ),
        SectionTitle(app.t('Appearance')),
        Card(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            ListTile(title: Text(app.t('Accent colour'))),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: Wrap(spacing: 10, runSpacing: 10, children: [
                for (final e in accentColors.entries)
                  Tooltip(
                    message: app.t(e.key),
                    child: InkWell(
                      customBorder: const CircleBorder(),
                      onTap: () => app.setPref('accent', e.key),
                      child: CircleAvatar(
                        radius: 18,
                        backgroundColor: e.value,
                        child: app.accentName == e.key
                            ? const Icon(Icons.check, color: Colors.white, size: 18)
                            : null,
                      ),
                    ),
                  ),
              ]),
            ),
            ListTile(
              title: Text(app.t('Theme')),
              trailing: DropdownButton<String>(
                value: app.prefs.getString('theme') ?? 'system',
                underline: const SizedBox.shrink(),
                items: [
                  DropdownMenuItem(value: 'system', child: Text(app.t('Same as phone'))),
                  DropdownMenuItem(value: 'light', child: Text(app.t('Light'))),
                  DropdownMenuItem(value: 'dark', child: Text(app.t('Dark'))),
                ],
                onChanged: (v) => app.setPref('theme', v ?? 'system'),
              ),
            ),
            ListTile(
              title: Text(app.t('Language')),
              trailing: DropdownButton<String>(
                value: app.lang,
                underline: const SizedBox.shrink(),
                items: const [
                  DropdownMenuItem(value: 'en', child: Text('English')),
                  DropdownMenuItem(value: 'fr', child: Text('Français')),
                  DropdownMenuItem(value: 'ar', child: Text('العربية')),
                ],
                onChanged: (v) => app.setPref('lang', v ?? 'en'),
              ),
            ),
            ListTile(
              title: Text(app.t('Budget currency')),
              trailing: DropdownButton<String>(
                value: currencies.contains(app.repo.baseCurrency)
                    ? app.repo.baseCurrency
                    : null,
                underline: const SizedBox.shrink(),
                items: [for (final c in currencies) DropdownMenuItem(value: c, child: Text(c))],
                onChanged: (v) {
                  if (v == null) return;
                  app.app.setSetting('base_currency', v);
                  app.changed(sync: false);
                },
              ),
            ),
          ]),
        ),
        SectionTitle(app.t('Notifications')),
        Card(
          child: Column(children: [
            SwitchListTile(
              secondary: const Icon(Icons.event_repeat_outlined),
              title: Text(app.t('Bill reminders')),
              subtitle: Text(app.t('The day before a bill or recurring payment is due.')),
              value: app.billReminders,
              onChanged: (v) async {
                if (v) await Notifier.requestPermission();
                await app.setFlag('bill_reminders', v);
              },
            ),
            SwitchListTile(
              secondary: const Icon(Icons.warning_amber_rounded),
              title: Text(app.t('Over-budget alerts')),
              subtitle: Text(app.t('When a category you budgeted for is overspent.')),
              value: app.budgetAlerts,
              onChanged: (v) async {
                if (v) await Notifier.requestPermission();
                await app.setFlag('budget_alerts', v);
              },
            ),
          ]),
        ),
        SectionTitle(app.t('About')),
        Card(
          child: Column(children: [
            ListTile(
              title: Text('Personal Finance Intelligence $appVersion'),
              subtitle: Text(app.t(
                  'Everything is stored on this phone. Sync files are encrypted with your passphrase before they reach your cloud drive.')),
            ),
            SwitchListTile(
              secondary: const Icon(Icons.system_update_outlined),
              title: Text(app.t('Check for updates')),
              subtitle: Text(app.t('Once a day, asks GitHub whether a newer version is out. Nothing about you or your data is sent.')),
              value: app.updateCheck,
              onChanged: (v) => app.setFlag('update_check', v),
            ),
            ListTile(
              leading: const Icon(Icons.open_in_new_rounded),
              title: Text(app.t('Check now')),
              onTap: () async {
                final messenger = ScaffoldMessenger.of(context);
                final v = await newerVersion(app, force: true);
                messenger.showSnackBar(SnackBar(
                  content: Text(v == null
                      ? app.t('PFI is up to date.')
                      : app.t('PFI {v} is available.', {'v': v})),
                  action: v == null
                      ? null
                      : SnackBarAction(
                          label: app.t('Download'),
                          onPressed: () => launchUrl(Uri.parse(releasesPage),
                              mode: LaunchMode.externalApplication)),
                ));
              },
            ),
            ListTile(
              leading: const Icon(Icons.gavel_outlined),
              title: Text(app.t('License')),
              subtitle: Text(app.t('Free to use. PFI may not be sold, redistributed or published in changed versions (PolyForm Strict).')),
            ),
          ]),
        ),
      ]),
    );
  }

  static String _when(Object? v, String lang) {
    if (v == null) return '—';
    final d = DateTime.tryParse('${v.toString().replaceAll(' ', 'T')}Z');
    if (d == null) return '$v';
    return DateFormat.MMMd(lang).add_Hm().format(d.toLocal());
  }
}

class SyncSetupPage extends StatefulWidget {
  const SyncSetupPage({super.key});
  @override
  State<SyncSetupPage> createState() => _SyncSetupPageState();
}

class _SyncSetupPageState extends State<SyncSetupPage> {
  CloudProvider provider = CloudProvider.onedrive;
  bool signedIn = false;
  bool busy = false;
  String? error;
  final pass = TextEditingController();
  final name = TextEditingController(text: 'Phone');

  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    final s = await CloudAuth(provider).signedIn;
    if (mounted) setState(() => signedIn = s);
  }

  Future<void> _run(Future<void> Function() job) async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await job();
    } catch (e) {
      error = '$e';
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = appOf(context);
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text(app.t('Set up sync'))),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Text(app.t('Choose your cloud drive'),
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Text(app.t('Use the same cloud drive as PFI on your PC. On the PC, the folder is {f}.',
            {'f': provider.pcFolder})),
        const SizedBox(height: 16),
        SegmentedButton<CloudProvider>(
          segments: [
            for (final p in CloudProvider.values)
              ButtonSegment(value: p, label: Text(p.title)),
          ],
          selected: {provider},
          onSelectionChanged: (s) {
            setState(() => provider = s.first);
            _check();
          },
        ),
        const SizedBox(height: 16),
        if (!provider.configured)
          Card(
            color: scheme.surfaceContainerHighest,
            child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(app.t('Not available in this build yet.'))),
          )
        else if (!signedIn)
          FilledButton.icon(
            onPressed: busy
                ? null
                : () => _run(() async {
                      await CloudAuth(provider).signIn();
                      await _check();
                    }),
            icon: const Icon(Icons.login),
            label: Text(app.t('Sign in to {p}', {'p': provider.title})),
          )
        else ...[
          ListTile(
            leading: Icon(Icons.check_circle,
                color: context.moneyColors.positive),
            title: Text(app.t('Signed in to {p}', {'p': provider.title})),
          ),
          TextField(
            controller: pass,
            obscureText: true,
            decoration: InputDecoration(
                labelText: app.t('Sync passphrase'),
                helperText: app.t(
                    'The passphrase you chose on your PC (or a new one if this phone is the first device).'),
                helperMaxLines: 3),
          ),
          const SizedBox(height: 12),
          TextField(
              controller: name,
              decoration: InputDecoration(labelText: app.t('Name of this phone'))),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: busy
                ? null
                : () => _run(() async {
                      await app.setUpSync(provider, pass.text, name.text);
                      if (context.mounted) {
                        Navigator.of(context).popUntil((r) => r.isFirst);
                      }
                    }),
            child: Text(app.t(busy ? 'Checking the passphrase…' : 'Start syncing')),
          ),
        ],
        if (error != null)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Text(error!, style: TextStyle(color: scheme.error)),
          ),
      ]),
    );
  }
}
