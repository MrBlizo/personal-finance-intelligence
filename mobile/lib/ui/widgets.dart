// Small building blocks shared by the screens.
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../state.dart';

AppState appOf(BuildContext context, {bool listen = true}) =>
    Provider.of<AppState>(context, listen: listen);

String money(BuildContext context, int minor, String currency,
    {bool sign = false}) {
  final lang = appOf(context, listen: false).lang;
  final f = NumberFormat('#,##0.00', lang == 'en' ? 'en_US' : lang);
  final text = f.format(minor.abs() / 100);
  final prefix = minor < 0 ? '−' : (sign && minor > 0 ? '+' : '');
  return '$prefix$currency $text';
}

/// Parses "12.50", "12,50" or "1'234.5" into minor units.
int? parseMinor(String text) {
  final t = text.replaceAll(RegExp(r"[\s'’]"), '').replaceAll(',', '.');
  final v = double.tryParse(t);
  return v == null ? null : (v * 100).round();
}

/// Default colours of earlier versions, shown in today's chart palette.
const _oldColours = {
  '0072B2': '4C6EF5', 'E69F00': 'F2994A', '009E73': '7CB518',
  'D55E00': 'EC5F9E', '56B4E9': '1FB5D8', 'CC79A7': '9775FA',
  'F0E442': 'C99A06', 'BE1818': 'EC5F9E', '6B7280': '8A8F98',
  '7C3AED': '9775FA', '0F766E': '1FB5D8', '9A3412': 'F2994A',
};

Color hexColor(String? hex, Color fallback) {
  if (hex == null || hex.length < 7) return fallback;
  final raw = hex.substring(1, 7).toUpperCase();
  final v = int.tryParse(_oldColours[raw] ?? raw, radix: 16);
  return v == null ? fallback : Color(0xFF000000 | v);
}

const _icons = <String, IconData>{
  'cart': Icons.shopping_cart_outlined, 'food': Icons.restaurant_outlined,
  'coffee': Icons.local_cafe_outlined, 'home': Icons.home_outlined,
  'bolt': Icons.bolt_outlined, 'wifi': Icons.wifi, 'phone': Icons.phone_iphone,
  'shield': Icons.shield_outlined, 'car': Icons.directions_car_outlined,
  'bus': Icons.directions_bus_outlined, 'fuel': Icons.local_gas_station_outlined,
  'taxi': Icons.local_taxi_outlined, 'health': Icons.favorite_outline,
  'doctor': Icons.medical_services_outlined, 'pill': Icons.medication_outlined,
  'shirt': Icons.checkroom_outlined, 'laptop': Icons.laptop_outlined,
  'bag': Icons.shopping_bag_outlined, 'games': Icons.sports_esports_outlined,
  'movie': Icons.movie_outlined, 'music': Icons.music_note_outlined,
  'ticket': Icons.confirmation_number_outlined, 'sport': Icons.sports_soccer_outlined,
  'gym': Icons.fitness_center_outlined, 'travel': Icons.flight_outlined,
  'beach': Icons.beach_access_outlined, 'book': Icons.menu_book_outlined,
  'school': Icons.school_outlined, 'bank': Icons.account_balance_outlined,
  'receipt': Icons.receipt_long_outlined, 'tax': Icons.gavel_outlined,
  'gift': Icons.card_giftcard_outlined, 'charity': Icons.volunteer_activism_outlined,
  'money': Icons.payments_outlined, 'work': Icons.work_outline,
  'salary': Icons.badge_outlined, 'savings': Icons.savings_outlined,
  'wallet': Icons.account_balance_wallet_outlined, 'invest': Icons.trending_up,
  'tag': Icons.sell_outlined, 'box': Icons.inventory_2_outlined,
  'pet': Icons.pets_outlined, 'tools': Icons.build_outlined,
  'toolbox': Icons.handyman_outlined, 'water': Icons.water_drop_outlined,
  'light': Icons.lightbulb_outline, 'building': Icons.apartment_outlined,
  'bed': Icons.bed_outlined, 'glasses': Icons.visibility_outlined,
  'umbrella': Icons.umbrella_outlined, 'document': Icons.description_outlined,
  'family': Icons.groups_outlined, 'star': Icons.auto_awesome_outlined,
  'other': Icons.circle_outlined,
};

// Same keywords as the PC (frontend/components/CategoryIcon.tsx).
final _guess = <(RegExp, String)>[
  (RegExp(r'grocer|épicer|courses|supermarch|بقال'), 'cart'),
  (RegExp(r'restaurant|dining|food|aliment|nourrit|طعام|مطعم'), 'food'),
  (RegExp(r'coffee|café|snack|قهوة'), 'coffee'),
  (RegExp(r'rent|loyer|housing|logement|mortgage|hypoth|سكن|إيجار'), 'home'),
  (RegExp(r'utilit|électric|electric|energy|énergie|كهرباء'), 'bolt'),
  (RegExp(r'internet|wifi'), 'wifi'),
  (RegExp(r'phone|téléphone|mobile|هاتف'), 'phone'),
  (RegExp(r'insurance|assurance|تأمين'), 'shield'),
  (RegExp(r'fuel|carbur|essence|gas|وقود'), 'fuel'),
  (RegExp(r'taxi|ride|uber'), 'taxi'),
  (RegExp(r'public transport|transport public|bus|train|tram|نقل'), 'bus'),
  (RegExp(r'car|voiture|auto|transport|سيارة'), 'car'),
  (RegExp(r'doctor|dentist|médecin|dentiste|طبيب'), 'doctor'),
  (RegExp(r'pharma|صيدل'), 'pill'),
  (RegExp(r'health|santé|صحة'), 'health'),
  (RegExp(r'cloth|vêtement|ملابس'), 'shirt'),
  (RegExp(r'electronic|électroni'), 'laptop'),
  (RegExp(r'shopping|achats|تسوق'), 'bag'),
  (RegExp(r'home & garden|maison|jardin'), 'home'),
  (RegExp(r'subscri|abonnement|اشتراك'), 'music'),
  (RegExp(r'entertain|divertis|loisir|leisure|ترفيه'), 'movie'),
  (RegExp(r'sport|gym|fitness|رياضة'), 'sport'),
  (RegExp(r'travel|voyage|holiday|سفر'), 'travel'),
  (RegExp(r'course|cours|education|éducation|school|تعليم'), 'school'),
  (RegExp(r'book|livre|كتب'), 'book'),
  (RegExp(r'bank|banque|fee|frais|بنك'), 'bank'),
  (RegExp(r'tax|impôt|ضريبة'), 'tax'),
  (RegExp(r'gift|cadeau|هدية'), 'gift'),
  (RegExp(r'donation|don\b|charity|تبرع'), 'charity'),
  (RegExp(r'family|famille|عائلة'), 'family'),
  (RegExp(r'salary|salaire|راتب'), 'salary'),
  (RegExp(r'bonus|prime|مكافأة'), 'money'),
  (RegExp(r'freelance|indépendant'), 'work'),
  (RegExp(r'dividend|interest|intérêt|invest'), 'invest'),
  (RegExp(r'refund|rembours|استرداد'), 'receipt'),
  (RegExp(r'saving|épargne|ادخار'), 'savings'),
  (RegExp(r'pet|animal|حيوان'), 'pet'),
  (RegExp(r'finance|مالية'), 'wallet'),
  (RegExp(r'other|autre|أخرى'), 'other'),
];

IconData categoryIcon(String? key, String? name) {
  if (key != null && _icons.containsKey(key)) return _icons[key]!;
  final n = (name ?? '').toLowerCase();
  for (final (re, k) in _guess) {
    if (re.hasMatch(n)) return _icons[k]!;
  }
  return n.isEmpty ? Icons.help_outline : Icons.sell_outlined;
}

class CategoryAvatar extends StatelessWidget {
  const CategoryAvatar(
      {super.key, this.icon, this.name, this.color, this.size = 44, this.square = false});
  final String? icon;
  final String? name;
  final String? color;
  final double size;

  /// A rounded square tile instead of a circle (budget lists).
  final bool square;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final c = hexColor(color, scheme.primary);
    return Container(
      width: size,
      height: size,
      decoration: square
          ? BoxDecoration(
              color: c.withValues(alpha: 0.18),
              borderRadius: BorderRadius.circular(size * 0.32))
          : BoxDecoration(color: c.withValues(alpha: 0.18), shape: BoxShape.circle),
      child: Icon(categoryIcon(icon, name), size: size * 0.5, color: c),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.action});
  final String text;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 20, 4, 8),
        child: Row(children: [
          Expanded(
              child: Text(text,
                  style: Theme.of(context)
                      .textTheme
                      .titleMedium
                      ?.copyWith(fontWeight: FontWeight.w700))),
          if (action != null) action!,
        ]),
      );
}

class AmountText extends StatelessWidget {
  const AmountText(this.minor, this.currency, {super.key, this.style});
  final int minor;
  final String currency;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final color = minor > 0 ? Colors.green.shade600 : scheme.onSurface;
    return Text(money(context, minor, currency, sign: true),
        style: (style ?? Theme.of(context).textTheme.titleSmall)
            ?.copyWith(color: color, fontWeight: FontWeight.w700));
  }
}

String dayLabel(BuildContext context, DateTime d) {
  final app = appOf(context, listen: false);
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final day = DateTime(d.year, d.month, d.day);
  if (day == today) return app.t('Today');
  if (day == today.subtract(const Duration(days: 1))) return app.t('Yesterday');
  return DateFormat.yMMMMEEEEd(app.lang).format(d);
}
