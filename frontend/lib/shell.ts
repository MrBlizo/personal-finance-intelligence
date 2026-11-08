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
