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
        winrt::Microsoft::UI::Xaml::Window window{ nullptr };
        HANDLE m_instanceMutex{ nullptr };
    };
}
