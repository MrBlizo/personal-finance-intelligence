#include "pch.h"
#include "Backend.h"

#include <appmodel.h>
#include <bcrypt.h>
#include <winhttp.h>
#include <winrt/Windows.Storage.h>
#include <winsock2.h>
#include <ws2tcpip.h>

#include <fstream>
#include <sstream>
#include <vector>

namespace fs = std::filesystem;

namespace pfi
{
    namespace
    {
        std::wstring Expand(std::wstring const& s)
        {
            DWORD n = ExpandEnvironmentStringsW(s.c_str(), nullptr, 0);
            std::wstring out(n, L'\0');
            ExpandEnvironmentStringsW(s.c_str(), out.data(), n);
            if (!out.empty() && out.back() == L'\0') out.pop_back();
            return out;
        }

        std::wstring IniValue(fs::path const& ini, wchar_t const* key, std::wstring const& def)
        {
            if (!fs::exists(ini)) return Expand(def);
            wchar_t buf[2048]{};
            GetPrivateProfileStringW(L"Backend", key, def.c_str(), buf, 2048, ini.c_str());
            return Expand(buf);
        }

        fs::path Resolve(fs::path const& base, std::wstring const& value)
        {
            fs::path p(value);
            if (p.is_relative()) p = base / p;
            std::error_code ec;
            auto c = fs::weakly_canonical(p, ec);
            return ec ? p : c;
        }

        int FreePort()
        {
            WSADATA wsa{};
            WSAStartup(MAKEWORD(2, 2), &wsa);
            SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
            sockaddr_in addr{};
            addr.sin_family = AF_INET;
            inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
            addr.sin_port = 0;
            int port = 0;
            if (s != INVALID_SOCKET && bind(s, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == 0)
            {
                int len = sizeof(addr);
                getsockname(s, reinterpret_cast<sockaddr*>(&addr), &len);
                port = ntohs(addr.sin_port);
            }
            if (s != INVALID_SOCKET) closesocket(s);
            WSACleanup();
            return port ? port : 8765;
        }

        std::wstring RandomToken()
        {
            unsigned char bytes[24]{};
            BCryptGenRandom(nullptr, bytes, sizeof(bytes), BCRYPT_USE_SYSTEM_PREFERRED_RNG);
            static wchar_t const hex[] = L"0123456789abcdef";
            std::wstring out;
            for (unsigned char b : bytes)
            {
                out += hex[b >> 4];
                out += hex[b & 15];
            }
            return out;
        }

        std::wstring LastErrorText(DWORD code)
        {
            wchar_t* msg = nullptr;
            FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
                           FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, code, 0,
                           reinterpret_cast<LPWSTR>(&msg), 0, nullptr);
            std::wstring s = msg ? msg : L"unknown error";
            if (msg) LocalFree(msg);
            while (!s.empty() && (s.back() == L'\n' || s.back() == L'\r')) s.pop_back();
            return s + L" (code " + std::to_wstring(code) + L")";
        }
    }

    bool IsPackaged()
    {
        UINT32 length = 0;
        return GetCurrentPackageFullName(&length, nullptr) != APPMODEL_ERROR_NO_PACKAGE;
    }

    fs::path ExeDir()
    {
        std::wstring buf(MAX_PATH, L'\0');
        DWORD n = 0;
        while ((n = GetModuleFileNameW(nullptr, buf.data(), static_cast<DWORD>(buf.size()))) == buf.size())
            buf.resize(buf.size() * 2);
        buf.resize(n);
        return fs::path(buf).parent_path();
    }

    BackendConfig LoadConfig()
    {
        fs::path exeDir = ExeDir();
        fs::path ini = exeDir / L"pfi.ini";
        BackendConfig c;
        c.exe = Resolve(exeDir, IniValue(ini, L"Exe", L"backend\\pfi-api.exe"));
        c.args = IniValue(ini, L"Args", L"");
        c.workDir = Resolve(exeDir, IniValue(ini, L"WorkDir", L"backend"));
        c.pgBin = Resolve(exeDir, IniValue(ini, L"PgBin", L"pgsql\\bin"));
        c.webDir = Resolve(exeDir, IniValue(ini, L"WebDir", L"web"));
        c.dataDir = Resolve(exeDir, IniValue(ini, L"DataDir",
                                             L"%LOCALAPPDATA%\\PersonalFinanceIntelligence"));
        if (IsPackaged())
        {
            // Microsoft Store (MSIX) install: keep the data in the package's
            // own storage. It is removed with the app and never mixes with a
            // copy installed from PFI-Setup.exe.
            try
            {
                auto local = winrt::Windows::Storage::ApplicationData::Current().LocalFolder().Path();
                c.dataDir = fs::path(std::wstring(local)) / L"PersonalFinanceIntelligence";
            }
            catch (...)
            {
            }
        }
        return c;
    }

    Backend::Backend(BackendConfig cfg) : m_cfg(std::move(cfg)) {}

    Backend::~Backend()
    {
        Stop();
    }

    std::wstring Backend::Start()
    {
        if (!fs::exists(m_cfg.exe))
            return L"The backend program was not found at \"" + m_cfg.exe.wstring() +
                   L"\". The installation is incomplete; reinstall Personal Finance "
                   L"Intelligence (or fix the Exe= entry in pfi.ini).";
        if (!fs::exists(m_cfg.pgBin / L"pg_ctl.exe"))
            return L"The bundled PostgreSQL was not found in \"" + m_cfg.pgBin.wstring() +
                   L"\". Reinstall the app, or set PgBin= in pfi.ini to a PostgreSQL "
                   L"bin folder.";

        std::error_code ec;
        fs::create_directories(LogDir(), ec);
        if (ec)
            return L"Cannot create the data folder \"" + LogDir().wstring() + L"\": " +
                   std::wstring(ec.message().begin(), ec.message().end()) +
                   L". Check that your user account can write to it.";

        m_port = FreePort();
        m_token = RandomToken();
        SetEnvironmentVariableW(L"PFI_API_TOKEN", m_token.c_str());
        SetEnvironmentVariableW(L"PFI_PG_BIN", m_cfg.pgBin.c_str());
        SetEnvironmentVariableW(L"PFI_FRONTEND_DIST", m_cfg.webDir.c_str());
        SetEnvironmentVariableW(L"PFI_DATA_DIR", m_cfg.dataDir.c_str());
        SetEnvironmentVariableW(L"PYTHONUNBUFFERED", L"1");
        SetEnvironmentVariableW(L"PYTHONIOENCODING", L"utf-8");

        SECURITY_ATTRIBUTES sa{ sizeof(sa), nullptr, TRUE };
        fs::path consoleLog = LogDir() / L"api-console.log";
        HANDLE log = CreateFileW(consoleLog.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                 &sa, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        HANDLE nul = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa,
                                 OPEN_EXISTING, 0, nullptr);

        std::wstring cmd = L"\"" + m_cfg.exe.wstring() + L"\" ";
        if (!m_cfg.args.empty()) cmd += m_cfg.args + L" ";
        cmd += L"--port " + std::to_wstring(m_port) + L" --log-file \"" +
               (LogDir() / L"api.log").wstring() + L"\"";

        m_job = CreateJobObjectW(nullptr, nullptr);
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(m_job, JobObjectExtendedLimitInformation, &limits, sizeof(limits));

        STARTUPINFOW si{ sizeof(si) };
        si.dwFlags = STARTF_USESTDHANDLES;
        si.hStdInput = nul;
        si.hStdOutput = log;
        si.hStdError = log;
        PROCESS_INFORMATION pi{};
        std::vector<wchar_t> cmdBuf(cmd.begin(), cmd.end());
        cmdBuf.push_back(L'\0');
        BOOL ok = CreateProcessW(nullptr, cmdBuf.data(), nullptr, nullptr, TRUE,
                                 CREATE_NO_WINDOW | CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT,
                                 nullptr, m_cfg.workDir.c_str(), &si, &pi);
        DWORD err = GetLastError();
        if (log != INVALID_HANDLE_VALUE) CloseHandle(log);
        if (nul != INVALID_HANDLE_VALUE) CloseHandle(nul);
        if (!ok)
            return L"Could not start the backend (" + LastErrorText(err) + L").\nCommand: " + cmd +
                   L"\nAn antivirus program may be blocking it; allow PFI and try again.";
        AssignProcessToJobObject(m_job, pi.hProcess);
        ResumeThread(pi.hThread);
        CloseHandle(pi.hThread);
        m_process = pi.hProcess;
        return L"";
    }

    std::wstring Backend::TailOfLog() const
    {
        for (auto name : { L"api.log", L"api-console.log" })
        {
            std::ifstream f(LogDir() / name, std::ios::binary);
            if (!f) continue;
            std::string all((std::istreambuf_iterator<char>(f)), {});
            if (all.empty()) continue;
            if (all.size() > 1500) all = all.substr(all.size() - 1500);
            int n = MultiByteToWideChar(CP_UTF8, 0, all.data(), static_cast<int>(all.size()), nullptr, 0);
            std::wstring w(n, L'\0');
            MultiByteToWideChar(CP_UTF8, 0, all.data(), static_cast<int>(all.size()), w.data(), n);
            return w;
        }
        return L"(no log output)";
    }

    std::wstring Backend::WaitReady(int timeoutSeconds)
    {
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(timeoutSeconds);
        while (std::chrono::steady_clock::now() < deadline)
        {
            if (WaitForSingleObject(m_process, 0) == WAIT_OBJECT_0)
            {
                DWORD code = 0;
                GetExitCodeProcess(m_process, &code);
                return L"The backend stopped unexpectedly (exit code " + std::to_wstring(code) +
                       L"). Last log lines:\n\n" + TailOfLog();
            }
            if (LocalHttp(L"GET", m_port, L"/api/health", L"", 1500) == 200) return L"";
            Sleep(300);
        }
        return L"The backend did not become ready within " + std::to_wstring(timeoutSeconds) +
               L" seconds. Last log lines:\n\n" + TailOfLog();
    }

    void Backend::Stop()
    {
        if (m_process)
        {
            if (WaitForSingleObject(m_process, 0) == WAIT_TIMEOUT)
            {
                LocalHttp(L"POST", m_port, L"/api/system/shutdown", m_token, 3000);
                WaitForSingleObject(m_process, 15000);
            }
            CloseHandle(m_process);
            m_process = nullptr;
        }
        if (m_job)
        {
            CloseHandle(m_job);  // kills anything still running in the job
            m_job = nullptr;
        }
    }

    int LocalHttp(wchar_t const* method, int port, wchar_t const* path,
                  std::wstring const& token, int timeoutMs, std::string* body)
    {
        int status = -1;
        HINTERNET session = WinHttpOpen(L"PFI/1.0", WINHTTP_ACCESS_TYPE_NO_PROXY,
                                        WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
        if (!session) return -1;
        WinHttpSetTimeouts(session, timeoutMs, timeoutMs, timeoutMs, timeoutMs);
        HINTERNET conn = WinHttpConnect(session, L"127.0.0.1", static_cast<INTERNET_PORT>(port), 0);
        HINTERNET req = conn ? WinHttpOpenRequest(conn, method, path, nullptr, WINHTTP_NO_REFERER,
                                                  WINHTTP_DEFAULT_ACCEPT_TYPES, 0) : nullptr;
        if (req)
        {
            std::wstring headers;
            if (!token.empty()) headers = L"X-PFI-Token: " + token + L"\r\n";
            BOOL sent = WinHttpSendRequest(req,
                                           headers.empty() ? WINHTTP_NO_ADDITIONAL_HEADERS : headers.c_str(),
                                           headers.empty() ? 0 : static_cast<DWORD>(-1L),
                                           WINHTTP_NO_REQUEST_DATA, 0, 0, 0);
            if (sent && WinHttpReceiveResponse(req, nullptr))
            {
                DWORD code = 0, size = sizeof(code);
                if (WinHttpQueryHeaders(req, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                                        WINHTTP_HEADER_NAME_BY_INDEX, &code, &size, WINHTTP_NO_HEADER_INDEX))
                    status = static_cast<int>(code);
                if (body)
                {
                    body->clear();
                    DWORD avail = 0;
                    while (WinHttpQueryDataAvailable(req, &avail) && avail > 0)
                    {
                        std::string chunk(avail, '\0');
                        DWORD read = 0;
                        if (!WinHttpReadData(req, chunk.data(), avail, &read) || read == 0) break;
                        body->append(chunk.data(), read);
                    }
                }
            }
            WinHttpCloseHandle(req);
        }
        if (conn) WinHttpCloseHandle(conn);
        WinHttpCloseHandle(session);
        return status;
    }
}
