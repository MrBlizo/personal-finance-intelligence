#pragma once
// Launches and supervises the Python backend (pfi-api.exe).
//
// The backend runs inside a Win32 job object with KILL_ON_JOB_CLOSE, so it
// can never outlive PFI.exe. On a normal close we first ask it to shut down
// gracefully so the database file is closed cleanly.

#include <filesystem>
#include <string>

namespace pfi
{
    struct BackendConfig
    {
        std::filesystem::path exe;      // pfi-api.exe, or python.exe in dev
        std::wstring args;              // extra arguments, e.g. "run.py"
        std::filesystem::path workDir;  // working directory of the backend
        std::filesystem::path webDir;   // static Next.js export
        std::filesystem::path dataDir;  // %LOCALAPPDATA%\PersonalFinanceIntelligence
    };

    // Folder containing PFI.exe.
    std::filesystem::path ExeDir();

    // True when running from an MSIX package (Microsoft Store install).
    bool IsPackaged();

    // Reads pfi.ini next to PFI.exe (optional) on top of the installed layout.
    BackendConfig LoadConfig();

    class Backend
    {
    public:
        explicit Backend(BackendConfig cfg);
        ~Backend();
        Backend(Backend const&) = delete;
        Backend& operator=(Backend const&) = delete;

        // Starts the process. Returns an empty string on success, otherwise
        // a message explaining what failed and how to fix it.
        std::wstring Start();

        // Blocks until /api/health answers 200, the process exits, or the
        // timeout passes. Returns an empty string when ready.
        std::wstring WaitReady(int timeoutSeconds);

        // Graceful shutdown, then kills anything left in the job.
        void Stop();

        int Port() const { return m_port; }
        std::wstring const& Token() const { return m_token; }
        std::filesystem::path LogDir() const { return m_cfg.dataDir / L"logs"; }
        BackendConfig const& Config() const { return m_cfg; }

    private:
        std::wstring TailOfLog() const;

        BackendConfig m_cfg;
        HANDLE m_job{ nullptr };
        HANDLE m_process{ nullptr };
        int m_port{ 0 };
        std::wstring m_token;
    };

    // Minimal HTTP client for 127.0.0.1 (returns status code, -1 on error).
    // When `body` is given, the response body (UTF-8) is stored in it.
    int LocalHttp(wchar_t const* method, int port, wchar_t const* path,
                  std::wstring const& token, int timeoutMs = 2000,
                  std::string* body = nullptr);
}
