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

    private:
        void SetupWindow();
        void StartBackend();
        void ShowError(std::wstring const& message);
        winrt::fire_and_forget OpenUi();
        void OnWebMessage(winrt::Microsoft::Web::WebView2::Core::CoreWebView2 const& sender,
                          winrt::Microsoft::Web::WebView2::Core::CoreWebView2WebMessageReceivedEventArgs const& args);
        void SelectNavItem(std::wstring const& path);
        bool IsAppUrl(winrt::hstring const& uri) const;

        std::unique_ptr<pfi::Backend> m_backend;
        bool m_syncingNav{ false };
        bool m_started{ false };
    };
}

namespace winrt::PFI::factory_implementation
{
    struct MainWindow : MainWindowT<MainWindow, implementation::MainWindow>
    {
    };
}
