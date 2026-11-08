#pragma once
// The few texts shown by the native shell itself (lock screen, notifications,
// start-up), in the three UI languages. The web screens have their own
// dictionaries; this file only covers what is drawn before or outside them.

#include <string>
#include <string_view>

namespace pfi
{
    enum class Text
    {
        LockTitle, LockBody, Unlock, HelloPrompt, HelloFailed, HelloUnavailable,
        DueToday, DueTomorrow, DueInDays, PostedAutomatically, MoreDue,
        Starting, StartingServices, Opening, FirstStartHint,
    };

    inline std::wstring Tr(std::wstring_view lang, Text id)
    {
        int l = lang == L"fr" ? 1 : lang == L"ar" ? 2 : 0;
        static wchar_t const* const table[][3] = {
            { L"Personal Finance Intelligence is locked",
              L"Personal Finance Intelligence est verrouillé",
              L"تطبيق Personal Finance Intelligence مقفل" },
            { L"Unlock with Windows Hello to see your finances.",
              L"Déverrouillez avec Windows Hello pour voir vos finances.",
              L"افتح القفل باستخدام Windows Hello لعرض بياناتك المالية." },
            { L"Unlock", L"Déverrouiller", L"فتح القفل" },
            { L"Unlock Personal Finance Intelligence",
              L"Déverrouiller Personal Finance Intelligence",
              L"فتح قفل Personal Finance Intelligence" },
            { L"Verification was cancelled or failed. Try again.",
              L"La vérification a été annulée ou a échoué. Réessayez.",
              L"أُلغي التحقق أو فشل. حاول مرة أخرى." },
            { L"Windows Hello is not available on this PC. Set up a PIN, fingerprint or face in Windows Settings › Accounts › Sign-in options.",
              L"Windows Hello n'est pas disponible sur ce PC. Configurez un code PIN, une empreinte ou le visage dans Paramètres › Comptes › Options de connexion.",
              L"Windows Hello غير متاح على هذا الحاسوب. أعِدّ رمز PIN أو بصمة أو الوجه من الإعدادات › الحسابات › خيارات تسجيل الدخول." },
            { L"Due today", L"À payer aujourd'hui", L"مستحق اليوم" },
            { L"Due tomorrow", L"À payer demain", L"مستحق غداً" },
            { L"Due in %d days", L"À payer dans %d jours", L"مستحق بعد %d أيام" },
            { L"It will be posted automatically.", L"Il sera comptabilisé automatiquement.",
              L"سيتم تسجيله تلقائياً." },
            { L"%d more payments are due soon.", L"%d autres paiements arrivent à échéance.",
              L"%d دفعات أخرى مستحقة قريباً." },
            { L"Starting…", L"Démarrage…", L"جارٍ التشغيل…" },
            { L"Starting database and services…", L"Démarrage de la base de données et des services…",
              L"جارٍ تشغيل قاعدة البيانات والخدمات…" },
            { L"Opening…", L"Ouverture…", L"جارٍ الفتح…" },
            { L"The first start sets up your private database and can take up to a minute.",
              L"Le premier démarrage crée votre base de données privée et peut prendre jusqu'à une minute.",
              L"يُنشئ التشغيل الأول قاعدة بياناتك الخاصة وقد يستغرق حتى دقيقة." },
        };
        return table[static_cast<int>(id)][l];
    }

    // Swiss-style money formatting used in notifications: -1'850.00
    inline std::wstring Money(double v)
    {
        wchar_t buf[64];
        swprintf_s(buf, L"%.2f", v < 0 ? -v : v);
        std::wstring s(buf);
        auto dot = s.find(L'.');
        std::wstring intPart = s.substr(0, dot), out;
        int n = 0;
        for (auto it = intPart.rbegin(); it != intPart.rend(); ++it, ++n)
        {
            if (n && n % 3 == 0) out.insert(out.begin(), L'\'');
            out.insert(out.begin(), *it);
        }
        return (v < 0 ? L"-" : L"") + out + s.substr(dot);
    }
}
