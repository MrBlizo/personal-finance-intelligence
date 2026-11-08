#pragma once

#include "MainWindow.g.h"
#include "Backend.h"

namespace winrt::PFI::implementation
{
    struct MainWindow : MainWindowT<MainWindow>
    {
        MainWindow()
        {
            // Xaml objects should not call InitializeComponent during construction.
            // See https://github.com/microsoft/cppwinrt/tree/master/nuget#initializecomponent
        }

        void Root_Loaded(winrt::Windows::Foundation::IInspectable const& sender,
                         winrt::Microsoft::UI::Xaml::RoutedEventArgs const& args);
        void Nav_SelectionChanged(winrt::Microsoft::UI::Xaml::Controls::NavigationView const& sender,
                                  winrt::Microsoft::UI::Xaml::Controls::NavigationViewSelectionChangedEventArgs const& args);
        void OpenLogs_Click(winrt::Windows::Foundation::IInspectable const& sender,
                            winrt::Microsoft::UI::Xaml::RoutedEventArgs const& args);
        void Unlock_Click(winrt::Windows::Foundation::IInspectable const& sender,
                          winrt::Microsoft::UI::Xaml::RoutedEventArgs const& args);

        // Called by App on the UI thread when a notification is clicked.
        void OnNotificationInvoked(std::wstring const& path);

        // Set by App before activation: first page to show (e.g. when the
        // app was started from a notification) and whether notifications
        // could be registered.
        void SetStartup(std::wstring const& path, bool notifications)
        {
            m_initialPath = path;
            m_notificationsEnabled = notifications;
        }

    private:
        void SetupWindow();
        void StartBackend();
        void ShowError(std::wstring const& message);
        winrt::fire_and_forget OpenUi();
        void OnWebMessage(winrt::Microsoft::Web::WebView2::Core::CoreWebView2 const& sender,
                          winrt::Microsoft::Web::WebView2::Core::CoreWebView2WebMessageReceivedEventArgs const& args);
        void SelectNavItem(std::wstring const& path);
        void NavigateWeb(std::wstring const& path);
        bool IsAppUrl(winrt::hstring const& uri) const;

        // Settings shared with the web UI (read from /api/settings).
        void LoadShellSettings();
        void ApplyLanguage(std::wstring const& lang,
                           winrt::Windows::Data::Json::JsonObject const* labels);

        // Windows Hello app lock.
        void Lock();
        winrt::fire_and_forget Unlock();
        winrt::Windows::Foundation::IAsyncOperation<bool> HelloAvailable();
        winrt::fire_and_forget ReplyHelloStatus();
        void CheckIdle();
        HWND WindowHandle();

        // Bill reminders as Windows notifications, and recurring auto-posting.
        void PollReminders();

        std::unique_ptr<pfi::Backend> m_backend;
        bool m_syncingNav{ false };
        bool m_started{ false };
        bool m_uiReady{ false };

        std::wstring m_initialPath;
        bool m_notificationsEnabled{ false };
        std::wstring m_lang{ L"en" };
        bool m_lockEnabled{ false };
        int m_lockMinutes{ 5 };
        bool m_locked{ false };
        bool m_verifying{ false };
        std::chrono::steady_clock::time_point m_minimizedSince{};
        bool m_wasMinimized{ false };

        winrt::Microsoft::UI::Dispatching::DispatcherQueueTimer m_idleTimer{ nullptr };
        winrt::Microsoft::UI::Dispatching::DispatcherQueueTimer m_reminderTimer{ nullptr };
    };
}

namespace winrt::PFI::factory_implementation
{
    struct MainWindow : MainWindowT<MainWindow, implementation::MainWindow>
    {
    };
}
