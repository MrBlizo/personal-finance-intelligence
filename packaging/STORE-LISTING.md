# Microsoft Store submission kit

Everything to paste into Partner Center for **Personal Finance Intelligence**.

## 1. Before the first build for the Store

1. Partner Center › Apps and games › your reserved app › **Product identity**.
2. Copy into `packaging/store.json`:
   - `identity_name` ← *Package/Identity/Name*
   - `publisher` ← *Package/Identity/Publisher* (starts with `CN=`)
   - `publisher_display_name` ← *Package/Properties/PublisherDisplayName*
3. Run `build.bat`. Upload `dist\PFI-<version>-x64.msix` under **Packages**.
   The Store signs the package; no certificate is needed.

## 2. Properties

| Field | Value |
|---|---|
| Category | Personal finance |
| Subcategory | Budgeting / Personal finance tools |
| Privacy policy URL | https://github.com/MrBlizo/personal-finance-intelligence/blob/main/PRIVACY.md |
| Website | https://github.com/MrBlizo/personal-finance-intelligence |
| Support contact | https://github.com/MrBlizo/personal-finance-intelligence/issues |
| Product declarations | Does not access/collect personal information outside the device; no in-app purchases |
| System requirements | x64, Windows 10 2004 (19041) or later; 1 GB disk; 4 GB RAM recommended |

**Age ratings questionnaire:** utility app; no user-generated content shared
with others, no violence, no purchases, no location, no chat. Expected rating:
3+ / Everyone.

**Restricted capability justification (runFullTrust):** "Personal Finance
Intelligence is a desktop (WinUI 3) app. It runs a local analysis service on
127.0.0.1, started and stopped by the app, that stores the user's finances in
a local SQLite database on their own PC. This component needs the
full-trust desktop model."

**Notes for certification:** "No account needed. Open the app, Home ›
'Load demo data' fills it with synthetic data to test every screen
(removable in Settings). First start takes a few seconds while the private
database is created."

## What's new in 0.5.1 (paste into "What's new in this version")

**English**

Version 0.5.1
• Test a backup: Settings › Backups › Test opens a backup in a temporary folder and compares every account balance, the number of transactions, the receipts and a random sample of transactions with your current data. Nothing is restored.
• After two weeks of use, PFI asks once whether you would like to rate it in the Microsoft Store.

**Français**

Version 0.5.1
• Tester une sauvegarde : Paramètres › Sauvegardes › Tester ouvre une sauvegarde dans un dossier temporaire et compare chaque solde, le nombre de transactions, les justificatifs et un échantillon de transactions avec vos données actuelles. Rien n'est restauré.
• Après deux semaines d'utilisation, PFI vous demande une seule fois si vous souhaitez le noter dans le Microsoft Store.

**العربية**

الإصدار 0.5.1
• اختبار نسخة احتياطية: الإعدادات › النسخ الاحتياطية › اختبار يفتح النسخة في مجلد مؤقت ويقارن كل رصيد وعدد المعاملات والإيصالات وعيّنة من المعاملات ببياناتك الحالية، دون استعادة أي شيء.
• بعد أسبوعين من الاستخدام، يسألك PFI مرة واحدة إن كنت ترغب في تقييمه في متجر Microsoft.

## 3. Store listing: English

**Product name:** Personal Finance Intelligence

**Short description (≤ 100):** Budgets, investments and cash-flow forecasts.
Private: your data stays on your PC.

**Description:**

Personal Finance Intelligence brings all your money together in one native
Windows 11 app, without an account and without the cloud.

• Accounts in any currency: checking, savings, cash, cards, investments and
loans, converted to the currency you report in.
• Import bank statements (CSV) from any bank. PFI remembers each format and
learns your categories from the transactions you categorise yourself.
• Bills & recurring payments: rent, salary and subscriptions post themselves
on the due date, and Windows reminds you before they are due.
• Budgets and savings goals with progress and projections.
• Investments with prices from Twelve Data, Alpha Vantage, stooq and
CoinGecko, money-weighted and
time-weighted returns, dividends and target allocation.
• Cash-flow forecast with probability bands, built from your own history.
• Insights: unusual expenses, subscriptions, category changes.
• Monthly PDF report, Excel export and net-worth history.
• Windows Hello app lock, automatic backups, light and dark mode.
• English, French and Arabic.

Your data is stored in a private database on your PC. PFI has no ads, no
tracking and no account. Source code: github.com/MrBlizo/personal-finance-intelligence

**Features (up to 20):**
- Multi-currency accounts with automatic exchange rates
- CSV import with presets and duplicate detection
- Categories learned from your own history
- Recurring payments that post themselves
- Bill reminders as Windows notifications
- Budgets with month-end projection
- Savings goals linked to accounts
- Investment tracking with XIRR and time-weighted return
- Target allocation and rebalancing amounts
- Cash-flow forecast with probability bands
- Spending insights
- Monthly PDF report and Excel export
- Windows Hello app lock
- Automatic backups and restore
- Works offline; no account

**Search terms (up to 7):** budget, personal finance, expense tracker,
investment tracker, cash flow, net worth, money manager

**Copyright:** © 2026 Ibrahim (MrBlizo)

## 4. Store listing: Français

**Description courte :** Budgets, placements et prévisions de trésorerie.
Privé : vos données restent sur votre PC.

**Description :**

Personal Finance Intelligence réunit tout votre argent dans une application
Windows 11 native, sans compte et sans cloud.

• Comptes dans toutes les devises : courant, épargne, espèces, cartes,
placements et prêts, convertis dans votre devise de référence.
• Import des relevés bancaires (CSV) de n'importe quelle banque. PFI retient
chaque format et apprend vos catégories à partir de celles que vous
attribuez vous-même.
• Factures et paiements récurrents : loyer, salaire et abonnements se
comptabilisent seuls à l'échéance, et Windows vous les rappelle à l'avance.
• Budgets et objectifs d'épargne avec suivi et projections.
• Placements avec cours Twelve Data, Alpha Vantage, stooq et CoinGecko,
rendements pondérés par les
capitaux et dans le temps, dividendes et répartition cible.
• Prévision de trésorerie avec intervalles de probabilité.
• Analyses : dépenses inhabituelles, abonnements, variations par catégorie.
• Rapport mensuel PDF, export Excel et évolution du patrimoine.
• Verrouillage Windows Hello, sauvegardes automatiques, mode clair et sombre.
• Français, anglais et arabe.

Vos données sont stockées dans une base privée sur votre PC. Sans publicité,
sans pistage, sans compte.

**Mots-clés :** budget, finances personnelles, suivi des dépenses,
placements, trésorerie, patrimoine, gestion d'argent

## 5. Store listing: العربية

**وصف قصير:** الميزانيات والاستثمارات وتوقعات التدفق النقدي. خاص: بياناتك
تبقى على حاسوبك.

**الوصف:**

يجمع Personal Finance Intelligence كل أموالك في تطبيق Windows 11 أصلي، بلا
حساب وبلا سحابة.

• حسابات بأي عملة: جارية، ادخار، نقد، بطاقات، استثمارات وقروض، محوّلة إلى
عملة التقارير التي تختارها.
• استيراد كشوف الحسابات البنكية (CSV) من أي بنك. يتذكر PFI صيغة كل ملف
ويتعلم فئاتك من المعاملات التي تصنفها بنفسك.
• الفواتير والدفعات المتكررة: الإيجار والراتب والاشتراكات تُسجَّل تلقائياً
في موعدها، ويذكّرك Windows قبل استحقاقها.
• ميزانيات وأهداف ادخار مع التقدم والتوقعات.
• استثمارات بأسعار من Twelve Data وAlpha Vantage وstooq وCoinGecko، عائد مرجّح بالأموال وزمنياً،
توزيعات الأرباح والتوزيع المستهدف.
• توقع التدفق النقدي مع نطاقات احتمالية.
• تحليلات: مصاريف غير عادية، اشتراكات، تغيرات حسب الفئة.
• تقرير شهري PDF وتصدير Excel وتطور صافي الثروة.
• قفل Windows Hello، نسخ احتياطي تلقائي، وضع فاتح وداكن.
• العربية والفرنسية والإنجليزية.

تُحفظ بياناتك في قاعدة بيانات خاصة على حاسوبك. بلا إعلانات وبلا تتبع وبلا
حساب.

**كلمات البحث:** ميزانية، مالية شخصية، تتبع المصاريف، استثمار، تدفق نقدي،
صافي الثروة، إدارة المال

## 6. Screenshots (required: at least 1, recommended 4–6)

1366×768 or larger, PNG. Use demo data (no real finances):
Home, Transactions, Investments (Performance tab), Bills & recurring,
Reports, Settings. Optional: one in Arabic and one in dark mode.
