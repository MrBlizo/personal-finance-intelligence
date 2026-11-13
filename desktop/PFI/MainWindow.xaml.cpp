#include "pch.h"
#include "MainWindow.xaml.h"
#if __has_include("MainWindow.g.cpp")
#include "MainWindow.g.cpp"
#endif
#include "Strings.h"

#include <fstream>

#include <microsoft.ui.xaml.window.h>       // IWindowNative
#include <UserConsentVerifierInterop.h>     // Windows Hello for desktop windows

using namespace winrt;
using namespace winrt::Microsoft::UI::Xaml;
using namespace winrt::Microsoft::UI::Xaml::Controls;
using namespace winrt::Microsoft::Web::WebView2::Core;
using namespace winrt::Windows::Data::Json;
using namespace winrt::Windows::Security::Credentials::UI;
namespace AppNotifications = winrt::Microsoft::Windows::AppNotifications;
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
            if (m_idleTimer) m_idleTimer.Stop();
            if (m_reminderTimer) m_reminderTimer.Stop();
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
        // Transparent page background, so the Mica layer of the window shows.
        SetEnvironmentVariableW(L"WEBVIEW2_DEFAULT_BACKGROUND_COLOR", L"0");

        m_backend = std::make_unique<pfi::Backend>(cfg);
        Status().Text(pfi::Tr(m_lang, pfi::Text::StartingServices));
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

    void MainWindow::LoadShellSettings()
    {
        std::string body;
        if (pfi::LocalHttp(L"GET", m_backend->Port(), L"/api/settings", m_backend->Token(),
                           3000, &body) != 200)
            return;
        try
        {
            auto obj = JsonObject::Parse(winrt::to_hstring(body));
            m_lockEnabled = obj.GetNamedString(L"app_lock", L"off") == L"hello";
            m_lockMinutes = static_cast<int>(obj.GetNamedNumber(L"lock_after_minutes", 5));
            ApplyLanguage(std::wstring(obj.GetNamedString(L"language", L"en")), nullptr);
            ApplyTheme(std::wstring(obj.GetNamedString(L"theme", L"system")));
        }
        catch (...)
        {
            // Keep the defaults: no lock, English shell texts.
        }
    }

    void MainWindow::ApplyTheme(std::wstring const& theme)
    {
        m_theme = (theme == L"light" || theme == L"dark") ? theme : L"system";
        auto element = m_theme == L"light" ? ElementTheme::Light
                     : m_theme == L"dark" ? ElementTheme::Dark : ElementTheme::Default;
        if (auto root = Content().try_as<FrameworkElement>()) root.RequestedTheme(element);
        try
        {
            using winrt::Microsoft::UI::Windowing::TitleBarTheme;
            AppWindow().TitleBar().PreferredTheme(
                m_theme == L"light" ? TitleBarTheme::Light
                : m_theme == L"dark" ? TitleBarTheme::Dark : TitleBarTheme::UseDefaultAppMode);
        }
        catch (...)
        {
            // Older Windows App SDK runtime: the caption buttons keep the system colours.
        }
        if (auto core = Web().CoreWebView2())
        {
            try
            {
                core.Profile().PreferredColorScheme(
                    m_theme == L"light" ? CoreWebView2PreferredColorScheme::Light
                    : m_theme == L"dark" ? CoreWebView2PreferredColorScheme::Dark
                    : CoreWebView2PreferredColorScheme::Auto);
            }
            catch (...)
            {
            }
        }
    }

    void MainWindow::ApplyLanguage(std::wstring const& lang, JsonObject const* labels)
    {
        m_lang = (lang == L"fr" || lang == L"ar") ? lang : L"en";
        auto dir = m_lang == L"ar" ? FlowDirection::RightToLeft : FlowDirection::LeftToRight;
        Nav().FlowDirection(dir);
        LockOverlay().FlowDirection(dir);
        Web().FlowDirection(FlowDirection::LeftToRight);   // the page handles its own direction
        LockTitle().Text(pfi::Tr(m_lang, pfi::Text::LockTitle));
        LockBody().Text(pfi::Tr(m_lang, pfi::Text::LockBody));
        UnlockButton().Content(box_value(pfi::Tr(m_lang, pfi::Text::Unlock)));
        if (!labels) return;
        auto relabel = [&](auto const& items)
        {
            for (auto const& item : items)
            {
                auto nvi = item.try_as<NavigationViewItem>();
                if (!nvi) continue;
                auto tag = unbox_value_or<hstring>(nvi.Tag(), L"");
                if (labels->HasKey(tag)) nvi.Content(box_value(labels->GetNamedString(tag)));
            }
        };
        relabel(Nav().MenuItems());
        relabel(Nav().FooterMenuItems());
    }

    winrt::fire_and_forget MainWindow::OpenUi()
    {
        auto strong = get_strong();
        LoadShellSettings();
        Status().Text(pfi::Tr(m_lang, pfi::Text::Opening));
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
        ApplyTheme(m_theme);   // the page colours, now that the WebView exists
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
        // Exports and backups: save straight to Downloads and let the page
        // confirm it, instead of showing the browser's download flyout.
        core.DownloadStarting([this](CoreWebView2 const&, CoreWebView2DownloadStartingEventArgs const& a)
        {
            a.Handled(true);
            ShellLog(L"download starting: " + std::wstring(a.ResultFilePath()));
            WatchDownload(a.DownloadOperation());
        });

        if (m_lockEnabled) Lock();
        std::wstring next = m_initialPath.empty() ? L"/" : m_initialPath;
        std::wstring url = L"http://127.0.0.1:" + std::to_wstring(m_backend->Port()) +
                           L"/auth/bootstrap?token=" + m_backend->Token() + L"&next=" + next;
        Web().Source(winrt::Windows::Foundation::Uri(url));
        if (!m_locked) Web().Visibility(Visibility::Visible);
        Splash().Visibility(Visibility::Collapsed);
        Nav().IsEnabled(true);
        SelectNavItem(next);
        m_uiReady = true;

        auto queue = DispatcherQueue();
        m_idleTimer = queue.CreateTimer();
        m_idleTimer.Interval(std::chrono::seconds(15));
        m_idleTimer.Tick([this](auto&&, auto&&) { CheckIdle(); });
        m_idleTimer.Start();
        m_reminderTimer = queue.CreateTimer();
        m_reminderTimer.Interval(std::chrono::minutes(60));
        m_reminderTimer.Tick([this](auto&&, auto&&) { PollReminders(); });
        m_reminderTimer.Start();
        PollReminders();

        if (m_locked) Unlock();
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

    void MainWindow::WatchDownload(CoreWebView2DownloadOperation const& op)
    {
        // StateChanged is not raised reliably for downloads in this host, so
        // keep the operation alive and poll its state until it settles.
        m_downloads.push_back(op);
        if (!m_downloadTimer)
        {
            m_downloadTimer = DispatcherQueue().CreateTimer();
            m_downloadTimer.Interval(std::chrono::milliseconds(250));
            m_downloadTimer.Tick([this](auto&&, auto&&)
            {
                std::vector<CoreWebView2DownloadOperation> pending;
                for (auto const& d : m_downloads)
                {
                    auto state = d.State();
                    if (state == CoreWebView2DownloadState::InProgress) pending.push_back(d);
                    else ShowDownload(std::wstring(d.ResultFilePath()),
                                      state == CoreWebView2DownloadState::Completed);
                }
                m_downloads = std::move(pending);
                if (m_downloads.empty()) m_downloadTimer.Stop();
            });
        }
        m_downloadTimer.Start();
    }

    void MainWindow::ShowDownload(std::wstring const& path, bool ok)
    {
        // The page shows the confirmation (XAML drawn over WebView2 can be
        // hidden behind it); the shell only remembers the file.
        m_lastDownload = ok ? path : L"";
        auto core = Web().CoreWebView2();
        if (!core) return;
        JsonObject msg;
        msg.SetNamedValue(L"type", JsonValue::CreateStringValue(L"downloaded"));
        msg.SetNamedValue(L"name", JsonValue::CreateStringValue(
            std::filesystem::path(path).filename().wstring()));
        msg.SetNamedValue(L"ok", JsonValue::CreateBooleanValue(ok));
        core.PostWebMessageAsJson(msg.Stringify());
        ShellLog(L"download notice sent: " + path);
    }

    void MainWindow::ShellLog(std::wstring const& line)
    {
        // Small diagnostics file next to the backend logs (logs\shell.log).
        if (!m_backend) return;
        std::ofstream f(m_backend->LogDir() / L"shell.log", std::ios::app | std::ios::binary);
        if (!f) return;
        auto utf8 = winrt::to_string(line);
        f << utf8 << "\r\n";
    }

    void MainWindow::OpenLastDownload(bool inFolder)
    {
        std::error_code ec;
        if (m_lastDownload.empty() || !std::filesystem::exists(m_lastDownload, ec)) return;
        // Start the viewer in the file's folder so it never inherits (and
        // locks) the app's own working directory.
        auto dir = std::filesystem::path(m_lastDownload).parent_path().wstring();
        if (inFolder)
        {
            std::wstring args = L"/select,\"" + m_lastDownload + L"\"";
            ShellExecuteW(nullptr, L"open", L"explorer.exe", args.c_str(), dir.c_str(), SW_SHOWNORMAL);
        }
        else
        {
            ShellExecuteW(nullptr, L"open", m_lastDownload.c_str(), nullptr, dir.c_str(), SW_SHOWNORMAL);
        }
    }

    void MainWindow::PickFolder(std::wstring const& start)
    {
        // The page cannot see folder paths, so the shell shows the Windows
        // folder dialog and sends the chosen path back ("" if cancelled).
        std::wstring chosen;
        try
        {
            auto dlg = winrt::create_instance<IFileOpenDialog>(CLSID_FileOpenDialog);
            DWORD opts{};
            dlg->GetOptions(&opts);
            dlg->SetOptions(opts | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST);
            if (!start.empty())
            {
                winrt::com_ptr<IShellItem> item;
                if (SUCCEEDED(SHCreateItemFromParsingName(start.c_str(), nullptr, IID_PPV_ARGS(item.put()))))
                    dlg->SetFolder(item.get());
            }
            if (SUCCEEDED(dlg->Show(WindowHandle())))
            {
                winrt::com_ptr<IShellItem> result;
                PWSTR path = nullptr;
                if (SUCCEEDED(dlg->GetResult(result.put())) &&
                    SUCCEEDED(result->GetDisplayName(SIGDN_FILESYSPATH, &path)))
                {
                    chosen = path;
                    CoTaskMemFree(path);
                }
            }
        }
        catch (...)
        {
            ShellLog(L"folder dialog failed");
        }
        auto core = Web().CoreWebView2();
        if (!core) return;
        JsonObject msg;
        msg.SetNamedValue(L"type", JsonValue::CreateStringValue(L"folderPicked"));
        msg.SetNamedValue(L"path", JsonValue::CreateStringValue(chosen));
        core.PostWebMessageAsJson(msg.Stringify());
    }

    void MainWindow::OnWebMessage(CoreWebView2 const&, CoreWebView2WebMessageReceivedEventArgs const& args)
    {
        try
        {
            auto obj = JsonObject::Parse(args.WebMessageAsJson());
            auto type = obj.GetNamedString(L"type", L"");
            if (type == L"route")
            {
                SelectNavItem(std::wstring(obj.GetNamedString(L"path", L"/")));
            }
            else if (type == L"language")
            {
                auto labels = obj.GetNamedObject(L"labels", JsonObject());
                ApplyLanguage(std::wstring(obj.GetNamedString(L"lang", L"en")), &labels);
            }
            else if (type == L"theme")
            {
                ApplyTheme(std::wstring(obj.GetNamedString(L"theme", L"system")));
            }
            else if (type == L"lockSettings")
            {
                m_lockEnabled = obj.GetNamedString(L"mode", L"off") == L"hello";
                m_lockMinutes = static_cast<int>(obj.GetNamedNumber(L"minutes", 5));
            }
            else if (type == L"lock")
            {
                if (m_lockEnabled) Lock();
            }
            else if (type == L"queryHello")
            {
                ReplyHelloStatus();
            }
            else if (type == L"downloadSeen")
            {
                ShellLog(L"page showed the download notice");
            }
            else if (type == L"openDownload" || type == L"showDownload")
            {
                OpenLastDownload(type == L"showDownload");
            }
            else if (type == L"pickFolder")
            {
                PickFolder(std::wstring(obj.GetNamedString(L"start", L"")));
            }
            else if (type == L"rate")
            {
                RequestRating();
            }
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

    void MainWindow::NavigateWeb(std::wstring const& path)
    {
        auto core = Web().CoreWebView2();
        if (!core) return;
        JsonObject msg;
        msg.SetNamedValue(L"type", JsonValue::CreateStringValue(L"navigate"));
        msg.SetNamedValue(L"path", JsonValue::CreateStringValue(path));
        core.PostWebMessageAsJson(msg.Stringify());
    }

    void MainWindow::Nav_SelectionChanged(NavigationView const&, NavigationViewSelectionChangedEventArgs const& args)
    {
        if (m_syncingNav || !args.SelectedItemContainer()) return;
        auto tag = winrt::unbox_value_or<winrt::hstring>(args.SelectedItemContainer().Tag(), L"/");
        NavigateWeb(std::wstring(tag));
    }

    void MainWindow::OpenLogs_Click(IInspectable const&, RoutedEventArgs const&)
    {
        auto dir = m_backend ? m_backend->LogDir() : pfi::LoadConfig().dataDir / L"logs";
        ShellExecuteW(nullptr, L"open", dir.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
    }

    // ------------------------------------------------------------------ lock
    HWND MainWindow::WindowHandle()
    {
        HWND hwnd{ nullptr };
        if (auto native = this->m_inner.try_as<::IWindowNative>())
            native->get_WindowHandle(&hwnd);
        return hwnd;
    }

    void MainWindow::Lock()
    {
        if (m_locked) return;
        m_locked = true;
        LockError().IsOpen(false);
        LockOverlay().Visibility(Visibility::Visible);
        Web().Visibility(Visibility::Collapsed);   // nothing readable behind the lock
    }

    void MainWindow::Unlock_Click(IInspectable const&, RoutedEventArgs const&)
    {
        Unlock();
    }

    winrt::Windows::Foundation::IAsyncOperation<bool> MainWindow::HelloAvailable()
    {
        try
        {
            auto availability = co_await UserConsentVerifier::CheckAvailabilityAsync();
            co_return availability == UserConsentVerifierAvailability::Available;
        }
        catch (...)
        {
            co_return false;
        }
    }

    winrt::fire_and_forget MainWindow::ReplyHelloStatus()
    {
        auto strong = get_strong();
        bool available = co_await HelloAvailable();
        if (auto core = Web().CoreWebView2())
        {
            JsonObject msg;
            msg.SetNamedValue(L"type", JsonValue::CreateStringValue(L"helloStatus"));
            msg.SetNamedValue(L"available", JsonValue::CreateBooleanValue(available));
            core.PostWebMessageAsJson(msg.Stringify());
        }
    }

    // ---------------------------------------------------------------- rating
    // Opens the Microsoft Store's own "rate and review" dialog. Installed
    // from the Store (packaged), StoreContext shows it over this window;
    // installed with PFI-Setup.exe (unpackaged), the Store app opens on the
    // review page instead. The page is told what happened.
    winrt::fire_and_forget MainWindow::RequestRating()
    {
        namespace Store = winrt::Windows::Services::Store;
        auto strong = get_strong();
        std::wstring status = L"error";
        try
        {
            if (pfi::IsPackaged())
            {
                auto store = Store::StoreContext::GetDefault();
                if (auto init = store.try_as<::IInitializeWithWindow>())
                    init->Initialize(WindowHandle());
                auto result = co_await store.RequestRateAndReviewAppAsync();
                switch (result.Status())
                {
                case Store::StoreRateAndReviewStatus::Succeeded:
                    status = result.WasUpdated() ? L"updated" : L"rated";
                    break;
                case Store::StoreRateAndReviewStatus::CanceledByUser:
                    status = L"canceled";
                    break;
                case Store::StoreRateAndReviewStatus::NetworkError:
                    status = L"network";
                    break;
                default:
                    status = L"error";
                    break;
                }
            }
            else
            {
                bool opened = co_await winrt::Windows::System::Launcher::LaunchUriAsync(
                    winrt::Windows::Foundation::Uri(L"ms-windows-store://review/?ProductId=9MZKW4H9F0J5"));
                status = opened ? L"opened" : L"error";
            }
        }
        catch (...)
        {
            status = L"error";
        }
        ShellLog(L"rating request: " + status);
        if (auto core = Web().CoreWebView2())
        {
            JsonObject msg;
            msg.SetNamedValue(L"type", JsonValue::CreateStringValue(L"rateResult"));
            msg.SetNamedValue(L"status", JsonValue::CreateStringValue(status));
            core.PostWebMessageAsJson(msg.Stringify());
        }
    }

    winrt::fire_and_forget MainWindow::Unlock()
    {
        if (m_verifying || !m_locked) co_return;
        m_verifying = true;
        auto strong = get_strong();
        auto result = UserConsentVerificationResult::Canceled;
        bool available = co_await HelloAvailable();
        if (!available)
        {
            // Without Windows Hello (e.g. it was removed after the lock was
            // switched on) the lock cannot be verified; open the app rather
            // than locking the user out of their own data.
            m_verifying = false;
            m_locked = false;
            LockOverlay().Visibility(Visibility::Collapsed);
            Web().Visibility(Visibility::Visible);
            co_return;
        }
        try
        {
            auto factory = winrt::get_activation_factory<UserConsentVerifier, ::IUserConsentVerifierInterop>();
            winrt::Windows::Foundation::IAsyncOperation<UserConsentVerificationResult> op{ nullptr };
            winrt::hstring message{ pfi::Tr(m_lang, pfi::Text::HelloPrompt) };
            winrt::check_hresult(factory->RequestVerificationForWindowAsync(
                WindowHandle(), reinterpret_cast<HSTRING>(winrt::get_abi(message)),
                winrt::guid_of<winrt::Windows::Foundation::IAsyncOperation<UserConsentVerificationResult>>(),
                winrt::put_abi(op)));
            result = co_await op;
        }
        catch (winrt::hresult_error const&)
        {
            result = UserConsentVerificationResult::DeviceNotPresent;
        }
        m_verifying = false;
        if (result == UserConsentVerificationResult::Verified)
        {
            m_locked = false;
            LockError().IsOpen(false);
            LockOverlay().Visibility(Visibility::Collapsed);
            Web().Visibility(Visibility::Visible);
        }
        else
        {
            LockError().Message(winrt::hstring(pfi::Tr(m_lang, pfi::Text::HelloFailed)));
            LockError().IsOpen(true);
        }
    }

    void MainWindow::CheckIdle()
    {
        using namespace std::chrono;
        bool minimized = false;
        if (auto presenter = AppWindow().Presenter().try_as<winrt::Microsoft::UI::Windowing::OverlappedPresenter>())
            minimized = presenter.State() == winrt::Microsoft::UI::Windowing::OverlappedPresenterState::Minimized;
        auto now = steady_clock::now();
        if (minimized && !m_wasMinimized) m_minimizedSince = now;
        m_wasMinimized = minimized;
        if (!m_lockEnabled || m_locked || m_lockMinutes <= 0) return;

        LASTINPUTINFO li{ sizeof(li) };
        GetLastInputInfo(&li);
        auto idle = milliseconds(GetTickCount() - li.dwTime);
        auto limit = minutes(m_lockMinutes);
        if (idle >= limit || (minimized && now - m_minimizedSince >= limit))
            Lock();
    }

    // ------------------------------------------------------- notifications
    void MainWindow::PollReminders()
    {
        if (!m_backend || !m_uiReady) return;
        // Book due auto-posting items first (also done at backend start-up).
        pfi::LocalHttp(L"POST", m_backend->Port(), L"/api/recurring/post-due", m_backend->Token(), 8000);
        if (!m_notificationsEnabled) return;
        std::string body;
        if (pfi::LocalHttp(L"POST", m_backend->Port(), L"/api/reminders/notifications",
                           m_backend->Token(), 8000, &body) != 200)
            return;
        try
        {
            auto items = JsonArray::Parse(winrt::to_hstring(body));
            uint32_t shown = 0;
            for (auto const& value : items)
            {
                if (shown == 3) break;
                auto o = value.GetObject();
                int days = static_cast<int>(o.GetNamedNumber(L"days_left", 0));
                std::wstring when;
                if (days <= 0) when = pfi::Tr(m_lang, pfi::Text::DueToday);
                else if (days == 1) when = pfi::Tr(m_lang, pfi::Text::DueTomorrow);
                else
                {
                    wchar_t buf[160];
                    swprintf_s(buf, pfi::Tr(m_lang, pfi::Text::DueInDays).c_str(), days);
                    when = buf;
                }
                std::wstring title = std::wstring(o.GetNamedString(L"name", L"")) + L" · " + when;
                std::wstring line = std::wstring(o.GetNamedString(L"currency", L"")) + L" " +
                                    pfi::Money(o.GetNamedNumber(L"amount", 0)) + L" · " +
                                    std::wstring(o.GetNamedString(L"account", L""));
                AppNotifications::Builder::AppNotificationBuilder builder;
                builder.AddArgument(L"page", L"/recurring/");
                builder.AddText(title);
                builder.AddText(line);
                if (o.GetNamedBoolean(L"auto_post", false))
                    builder.AddText(pfi::Tr(m_lang, pfi::Text::PostedAutomatically));
                AppNotifications::AppNotificationManager::Default().Show(builder.BuildNotification());
                ++shown;
            }
            if (items.Size() > shown)
            {
                wchar_t buf[160];
                swprintf_s(buf, pfi::Tr(m_lang, pfi::Text::MoreDue).c_str(),
                           static_cast<int>(items.Size() - shown));
                AppNotifications::Builder::AppNotificationBuilder builder;
                builder.AddArgument(L"page", L"/recurring/");
                builder.AddText(L"Personal Finance Intelligence");
                builder.AddText(buf);
                AppNotifications::AppNotificationManager::Default().Show(builder.BuildNotification());
            }
        }
        catch (...)
        {
            // A notification problem must never disturb the app.
        }
    }

    void MainWindow::OnNotificationInvoked(std::wstring const& path)
    {
        if (auto presenter = AppWindow().Presenter().try_as<winrt::Microsoft::UI::Windowing::OverlappedPresenter>())
        {
            if (presenter.State() == winrt::Microsoft::UI::Windowing::OverlappedPresenterState::Minimized)
                presenter.Restore();
        }
        Activate();
        SetForegroundWindow(WindowHandle());
        if (m_uiReady && !path.empty())
        {
            SelectNavItem(path);
            NavigateWeb(path);
        }
        else if (!path.empty())
        {
            m_initialPath = path;
        }
    }
}
