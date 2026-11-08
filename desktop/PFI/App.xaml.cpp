#include "pch.h"
#include "App.xaml.h"
#include "MainWindow.xaml.h"

using namespace winrt;
using namespace Microsoft::UI::Xaml;
namespace AppNotifications = winrt::Microsoft::Windows::AppNotifications;
namespace AppLifecycle = winrt::Microsoft::Windows::AppLifecycle;

namespace winrt::PFI::implementation
{
    namespace
    {
        std::wstring PageFromArguments(AppNotifications::AppNotificationActivatedEventArgs const& args)
        {
            auto map = args.Arguments();
            if (map && map.HasKey(L"page")) return std::wstring(map.Lookup(L"page"));
            return L"/recurring/";
        }
    }

    App::App()
    {
        // Xaml objects should not call InitializeComponent during construction.
        // See https://github.com/microsoft/cppwinrt/tree/master/nuget#initializecomponent
#if defined _DEBUG && !defined DISABLE_XAML_GENERATED_BREAK_ON_UNHANDLED_EXCEPTION
        UnhandledException([](IInspectable const&, UnhandledExceptionEventArgs const& e)
        {
            if (IsDebuggerPresent())
            {
                auto errorMessage = e.Message();
                __debugbreak();
            }
        });
#endif
    }

    App::~App()
    {
        if (m_notificationsRegistered)
        {
            try { AppNotifications::AppNotificationManager::Default().Unregister(); }
            catch (...) {}
        }
        if (m_instanceMutex) CloseHandle(m_instanceMutex);
    }

    void App::OnNotificationInvoked(AppNotifications::AppNotificationManager const&,
                                    AppNotifications::AppNotificationActivatedEventArgs const& args)
    {
        // Raised on a background thread: hand over to the UI thread.
        std::wstring page = PageFromArguments(args);
        if (!m_queue) return;
        m_queue.TryEnqueue([this, page]()
        {
            if (auto w = window.try_as<winrt::PFI::MainWindow>())
                winrt::get_self<implementation::MainWindow>(w)->OnNotificationInvoked(page);
        });
    }

    void App::OnLaunched([[maybe_unused]] LaunchActivatedEventArgs const& e)
    {
        // One instance only: two copies would share (and stop) the same
        // private database. A second launch brings the first window forward.
        m_instanceMutex = CreateMutexW(nullptr, TRUE,
            L"Local\\PersonalFinanceIntelligence.SingleInstance");
        if (GetLastError() == ERROR_ALREADY_EXISTS)
        {
            if (HWND existing = FindWindowW(nullptr, L"Personal Finance Intelligence"))
            {
                ShowWindow(existing, SW_RESTORE);
                SetForegroundWindow(existing);
            }
            Application::Current().Exit();
            return;
        }
        m_queue = winrt::Microsoft::UI::Dispatching::DispatcherQueue::GetForCurrentThread();

        // Bill reminders are shown as Windows notifications. Registration
        // can fail on unusual setups; the app then simply works without them.
        try
        {
            auto manager = AppNotifications::AppNotificationManager::Default();
            manager.NotificationInvoked({ this, &App::OnNotificationInvoked });
            manager.Register();
            m_notificationsRegistered = true;
        }
        catch (...)
        {
            m_notificationsRegistered = false;
        }

        std::wstring startPage;
        try
        {
            auto activated = AppLifecycle::AppInstance::GetCurrent().GetActivatedEventArgs();
            if (activated.Kind() == AppLifecycle::ExtendedActivationKind::AppNotification)
                startPage = PageFromArguments(
                    activated.Data().as<AppNotifications::AppNotificationActivatedEventArgs>());
        }
        catch (...)
        {
        }

        window = make<MainWindow>();
        if (auto w = window.try_as<winrt::PFI::MainWindow>())
            winrt::get_self<implementation::MainWindow>(w)->SetStartup(startPage, m_notificationsRegistered);
        window.Activate();
    }
}
