import { useEffect } from "react";
import Sidebar from "./components/Sidebar";
import WebViewArea from "./components/WebViewArea";
import { useAppStore } from "./store";

window.__inkBossActiveId = null;

export default function App() {
  const { loadConfig, loaded, activeServiceId } = useAppStore();

  useEffect(() => {
    const init = () => loadConfig();
    if (window.pywebview) {
      init();
    } else {
      window.addEventListener("pywebviewready", init, { once: true });
    }
  }, [loadConfig]);

  useEffect(() => {
    window.__inkBossActiveId = activeServiceId;
  }, [activeServiceId]);

  // モーダル等で Electron オーバーレイが前面に残らないよう
  useEffect(() => {
    const onErr = (e: Event) => {
      const d = (e as CustomEvent).detail;
      console.warn("[engine-error]", d);
    };
    window.addEventListener("engine-error", onErr);
    return () => window.removeEventListener("engine-error", onErr);
  }, []);

  if (!loaded) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-[#080810] text-white/40 text-sm font-mono">
        Loading…
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#080810]">
      <Sidebar />
      <WebViewArea />
    </div>
  );
}
