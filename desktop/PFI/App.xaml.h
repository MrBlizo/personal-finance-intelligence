#pragma once

#include "App.xaml.g.h"

namespace winrt::PFI::implementation
{
    struct App : AppT<App>
    {
        App();
        ~App();

        void OnLaunched(Microsoft::UI::Xaml::LaunchActivatedEventArgs const&);

    private:
        void OnNotificationInvoked(
            winrt::Microsoft::Windows::AppNotifications::AppNotificationManager const& sender,
            winrt::Microsoft::Windows::AppNotifications::AppNotificationActivatedEventArgs const& args);

        winrt::Microsoft::UI::Xaml::Window window{ nullptr };
        winrt::Microsoft::UI::Dispatching::DispatcherQueue m_queue{ nullptr };
        HANDLE m_instanceMutex{ nullptr };
        bool m_notificationsRegistered{ false };
    };
}
