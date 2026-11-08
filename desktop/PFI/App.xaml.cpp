#include "pch.h"
#include "App.xaml.h"
#include "MainWindow.xaml.h"

using namespace winrt;
using namespace Microsoft::UI::Xaml;

namespace winrt::PFI::implementation
{
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
        if (m_instanceMutex) CloseHandle(m_instanceMutex);
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
        window = make<MainWindow>();
        window.Activate();
    }
}
