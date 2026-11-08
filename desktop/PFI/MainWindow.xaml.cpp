#include "pch.h"
#include "MainWindow.xaml.h"
#if __has_include("MainWindow.g.cpp")
#include "MainWindow.g.cpp"
#endif

using namespace winrt;
using namespace winrt::Microsoft::UI::Xaml;
using namespace winrt::Microsoft::UI::Xaml::Controls;
using namespace winrt::Microsoft::Web::WebView2::Core;
namespace fs = std::filesystem;

namespace winrt::PFI::implementation
{
    void MainWindow::Root_Loaded(IInspectable const&, RoutedEventArgs const&)
    {
        if (m_started) return;
        m_started = true;
        SetupWindow();
        StartBackend();
    }

    void MainWindow::SetupWindow()
    {
        ExtendsContentIntoTitleBar(true);
        SetTitleBar(AppTitleBar());
        auto appWindow = AppWindow();
        appWindow.Resize({ 1440, 920 });
        auto icon = pfi::ExeDir() / L"pfi.ico";
        if (fs::exists(icon)) appWindow.SetIcon(icon.c_str());

        Closed([this](IInspectable const&, WindowEventArgs const&)
        {
            AppWindow().Hide();          // close instantly for the user
            if (m_backend) m_backend->Stop();
        });
    }

    void MainWindow::StartBackend()
    {
        auto cfg = pfi::LoadConfig();
        // WebView2 must not write next to PFI.exe (Program Files is read-only).
        auto webviewData = cfg.dataDir / L"WebView2";
        SetEnvironmentVariableW(L"WEBVIEW2_USER_DATA_FOLDER", webviewData.c_str());

        m_backend = std::make_unique<pfi::Backend>(cfg);
        Status().Text(L"Starting database and services…");
        std::wstring err = m_backend->Start();
        if (!err.empty())
        {
            ShowError(err);
            return;
        }
        auto weak = get_weak();
        auto queue = DispatcherQueue();
        pfi::Backend* backend = m_backend.get();
        std::thread([weak, queue, backend]()
        {
            std::wstring waitErr = backend->WaitReady(180);
            queue.TryEnqueue([weak, waitErr]()
            {
                if (auto self = weak.get())
                {
                    if (waitErr.empty()) self->OpenUi();
                    else self->ShowError(waitErr);
                }
            });
        }).detach();
    }

    winrt::fire_and_forget MainWindow::OpenUi()
    {
        auto strong = get_strong();
        Status().Text(L"Opening…");
        try
        {
            co_await Web().EnsureCoreWebView2Async();
        }
        catch (winrt::hresult_error const& e)
        {
            ShowError(L"The Microsoft Edge WebView2 Runtime could not be started (" +
                      std::wstring(e.message()) + L"). Install it from "
                      L"https://go.microsoft.com/fwlink/p/?LinkId=2124703 and restart the app.");
            co_return;
        }
        auto core = Web().CoreWebView2();
        auto settings = core.Settings();
        settings.IsStatusBarEnabled(false);
        settings.IsGeneralAutofillEnabled(false);
        settings.IsPasswordAutosaveEnabled(false);
#ifdef NDEBUG
        settings.AreDevToolsEnabled(false);
#endif
        core.WebMessageReceived({ this, &MainWindow::OnWebMessage });
        core.NavigationStarting([this](CoreWebView2 const&, CoreWebView2NavigationStartingEventArgs const& a)
        {
            if (!IsAppUrl(a.Uri()))
            {
                a.Cancel(true);
                winrt::Windows::System::Launcher::LaunchUriAsync(winrt::Windows::Foundation::Uri(a.Uri()));
            }
        });
        core.NewWindowRequested([](CoreWebView2 const&, CoreWebView2NewWindowRequestedEventArgs const& a)
        {
            a.Handled(true);
            winrt::Windows::System::Launcher::LaunchUriAsync(winrt::Windows::Foundation::Uri(a.Uri()));
        });

        std::wstring url = L"http://127.0.0.1:" + std::to_wstring(m_backend->Port()) +
                           L"/auth/bootstrap?token=" + m_backend->Token() + L"&next=/";
        Web().Source(winrt::Windows::Foundation::Uri(url));
        Web().Visibility(Visibility::Visible);
        Splash().Visibility(Visibility::Collapsed);
        Nav().IsEnabled(true);
        SelectNavItem(L"/");
    }

    bool MainWindow::IsAppUrl(winrt::hstring const& uri) const
    {
        std::wstring prefix = L"http://127.0.0.1:" + std::to_wstring(m_backend->Port()) + L"/";
        std::wstring u(uri);
        return u.rfind(prefix, 0) == 0 || u == L"about:blank";
    }

    void MainWindow::ShowError(std::wstring const& message)
    {
        Splash().Visibility(Visibility::Collapsed);
        ErrorBar().Message(winrt::hstring(message));
        ErrorBar().IsOpen(true);
    }

    void MainWindow::OnWebMessage(CoreWebView2 const&, CoreWebView2WebMessageReceivedEventArgs const& args)
    {
        try
        {
            auto obj = winrt::Windows::Data::Json::JsonObject::Parse(args.WebMessageAsJson());
            if (obj.GetNamedString(L"type", L"") == L"route")
                SelectNavItem(std::wstring(obj.GetNamedString(L"path", L"/")));
        }
        catch (...)
        {
            // Ignore malformed messages from the page.
        }
    }

    void MainWindow::SelectNavItem(std::wstring const& path)
    {
        std::wstring p = path.empty() ? L"/" : path;
        if (p.back() != L'/') p += L'/';
        auto match = [&](auto const& items) -> NavigationViewItem
        {
            for (auto const& item : items)
            {
                if (auto nvi = item.try_as<NavigationViewItem>())
                {
                    auto tag = winrt::unbox_value_or<winrt::hstring>(nvi.Tag(), L"");
                    if (std::wstring(tag) == p) return nvi;
                }
            }
            return nullptr;
        };
        NavigationViewItem found = match(Nav().MenuItems());
        if (!found) found = match(Nav().FooterMenuItems());
        if (found && Nav().SelectedItem() != found)
        {
            m_syncingNav = true;
            Nav().SelectedItem(found);
            m_syncingNav = false;
        }
    }

    void MainWindow::Nav_SelectionChanged(NavigationView const&, NavigationViewSelectionChangedEventArgs const& args)
    {
        if (m_syncingNav || !args.SelectedItemContainer()) return;
        auto tag = winrt::unbox_value_or<winrt::hstring>(args.SelectedItemContainer().Tag(), L"/");
        auto core = Web().CoreWebView2();
        if (!core) return;
        winrt::Windows::Data::Json::JsonObject msg;
        msg.SetNamedValue(L"type", winrt::Windows::Data::Json::JsonValue::CreateStringValue(L"navigate"));
        msg.SetNamedValue(L"path", winrt::Windows::Data::Json::JsonValue::CreateStringValue(tag));
        core.PostWebMessageAsJson(msg.Stringify());
    }

    void MainWindow::OpenLogs_Click(IInspectable const&, RoutedEventArgs const&)
    {
        auto dir = m_backend ? m_backend->LogDir() : pfi::LoadConfig().dataDir / L"logs";
        ShellExecuteW(nullptr, L"open", dir.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
    }
}
