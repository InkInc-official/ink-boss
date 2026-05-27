import { useEffect } from "react";
import Sidebar from "./components/Sidebar";
import WebViewArea from "./components/WebViewArea";
import { useAppStore } from "./store";

// グローバルにactiveIdを保持（モーダルから参照するため）
declare global {
  interface Window {
    __inkBossActiveId: string | null;
  }
}
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

  // activeServiceIdをグローバルに同期
  useEffect(() => {
    window.__inkBossActiveId = activeServiceId;
  }, [activeServiceId]);

  if (!loaded) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-[#080810]">
        <p className="text-white/30 font-mono text-sm animate-pulse">Loading...</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#080810] text-white">
      <Sidebar />
      <WebViewArea />
    </div>
  );
}
