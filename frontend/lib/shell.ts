// Bridge to the WinUI 3 shell (PFI.exe) through WebView2 messaging.
// Outside the shell (plain browser) every function is a no-op.

type WebView = {
  postMessage: (msg: unknown) => void;
  addEventListener: (t: "message", h: (e: { data: unknown }) => void) => void;
  removeEventListener: (t: "message",
    h: (e: { data: unknown }) => void) => void;
};

function webview(): WebView | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { chrome?: { webview?: WebView } };
  return w.chrome?.webview ?? null;
}

export const inShell = () => webview() !== null;

export function notifyRoute(path: string) {
  webview()?.postMessage({ type: "route", path });
}

export function onShellNavigate(cb: (path: string) => void): () => void {
  const wv = webview();
  if (!wv) return () => {};
  const handler = (e: { data: unknown }) => {
    const d = e.data as { type?: string; path?: string };
    if (d?.type === "navigate" && d.path) cb(d.path);
  };
  wv.addEventListener("message", handler);
  return () => wv.removeEventListener("message", handler);
}

/** Tell the shell the UI language so it can translate the navigation. */
export function notifyLanguage(lang: string, labels: Record<string, string>) {
  webview()?.postMessage({ type: "language", lang, labels });
}

/** Ask the shell to lock the app now (Windows Hello). */
export function requestLock() {
  webview()?.postMessage({ type: "lock" });
}

/** Tell the shell that app-lock settings changed. */
export function notifyLockSettings(mode: string, minutes: number) {
  webview()?.postMessage({ type: "lockSettings", mode, minutes });
}

/** Ask the shell whether Windows Hello is available on this PC. */
export function queryHello(): Promise<boolean | null> {
  const wv = webview();
  if (!wv) return Promise.resolve(null);
  return new Promise((resolve) => {
    const handler = (e: { data: unknown }) => {
      const d = e.data as { type?: string; available?: boolean };
      if (d?.type === "helloStatus") {
        wv.removeEventListener("message", handler);
        resolve(Boolean(d.available));
      }
    };
    wv.addEventListener("message", handler);
    wv.postMessage({ type: "queryHello" });
    setTimeout(() => { wv.removeEventListener("message", handler); resolve(null); }, 4000);
  });
}

export type ShellDownload = { name: string; ok: boolean };

/** Subscribe to files the shell saved to the Downloads folder. */
export function onShellDownload(cb: (d: ShellDownload) => void): () => void {
  const wv = webview();
  if (!wv) return () => {};
  const handler = (e: { data: unknown }) => {
    const d = e.data as { type?: string; name?: string; ok?: boolean };
    if (d?.type === "downloaded") {
      cb({ name: d.name ?? "", ok: Boolean(d.ok) });
      wv.postMessage({ type: "downloadSeen" });
    }
  };
  wv.addEventListener("message", handler);
  return () => wv.removeEventListener("message", handler);
}

/** Open the last saved file, or show it selected in File Explorer. */
export function openLastDownload(inFolder: boolean) {
  webview()?.postMessage({ type: inFolder ? "showDownload" : "openDownload" });
}
