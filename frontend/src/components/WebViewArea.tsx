import { useState } from "react";
import { useAppStore } from "../store";
import InkAide from "./InkAide";

export default function WebViewArea() {
  const { services, activeServiceId, hibernatedIds } = useAppStore();
  const activeService = services.find((s) => s.id === activeServiceId);
  const isHibernated = activeServiceId ? hibernatedIds.has(activeServiceId) : false;
  const showEmpty = !activeServiceId;
  const [aideOpen, setAideOpen] = useState(false);
  const [aideOk, setAideOk] = useState(false);

  const handleReload   = () => { if (activeServiceId && !isHibernated) window.pywebview?.api?.reload_service(activeServiceId); };
  const handleClose    = () => window.pywebview?.api?.close_window();
  const handleMinimize = () => window.pywebview?.api?.minimize_window();
  const handleMaximize = () => window.pywebview?.api?.toggle_maximize();

  // タイトルバーにURLを反映
  if (activeService?.url) {
    window.pywebview?.api?.update_title?.(activeService.url);
  } else {
    window.pywebview?.api?.update_title?.("Ink Boss");
  }

  const handleAideToggle = () => {
    const next = !aideOpen;
    setAideOpen(next);
    window.pywebview?.api?.set_aide_width?.(next ? 320 : 0);
  };

  const TopBar = () => (
    <div className="flex items-center h-10 bg-[#0a0a12] border-b border-white/5 px-4 gap-3 flex-shrink-0 cursor-default select-none"
      onMouseDown={(e: any) => {
        if ((e.target as HTMLElement).tagName !== "BUTTON") {
          window.pywebview?.api?.drag_start?.();
          const onUp = () => {
            window.pywebview?.api?.drag_end?.();
            window.removeEventListener("mouseup", onUp);
          };
          window.addEventListener("mouseup", onUp);
        }
      }}>
      <div className="flex items-center gap-1.5">
        <button onClick={handleClose}    className="w-3 h-3 rounded-full bg-white/20 hover:bg-red-500 transition-colors" />
        <button onClick={handleMinimize} className="w-3 h-3 rounded-full bg-white/15 hover:bg-yellow-400 transition-colors" />
        <button onClick={handleMaximize} className="w-3 h-3 rounded-full bg-white/10 hover:bg-green-400 transition-colors" />
      </div>
      <div className="flex-1 flex items-center justify-center">
        <span className="text-white/20 text-xs font-mono">{showEmpty ? "Ink Boss" : activeService?.url}</span>
      </div>
      <div className="flex items-center gap-2">
        {!showEmpty && (
          <button onClick={handleReload} className="text-white/30 hover:text-white/70 transition-colors w-6 h-6 flex items-center justify-center rounded-md hover:bg-white/5">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
          </button>
        )}
        <button onClick={handleAideToggle}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs transition-all ${aideOpen ? "bg-white/15 text-white border border-white/20" : "text-white/30 hover:text-white/70 hover:bg-white/5"}`}>
          {aideOk && <span className="text-[9px] text-green-400/70 font-mono">✓</span>}
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <span className="font-mono tracking-wide">Aide</span>
        </button>
      </div>
    </div>
  );

  if (showEmpty) {
    return (
      <div className="flex-1 flex flex-col bg-[#080810] overflow-hidden">
        <TopBar />
        <div className="flex-1 flex flex-col items-center justify-center select-none">
          <div className="flex flex-col items-center gap-6">
            <img src="/icon.png" alt="Ink Boss" className="w-24 h-24 object-cover rounded-2xl"
              style={{ filter: "grayscale(100%) brightness(1.3)" }}
              onError={(e) => { (e.target as HTMLImageElement).style.display="none"; }} />
            <div className="text-center space-y-2">
              <p className="font-display text-3xl tracking-[0.25em] text-white/70">INK BOSS</p>
              <p className="text-sm text-white/35 font-light leading-relaxed">左のサイドバーからサービスを選択するか<br />「+」でサービスを追加してください</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col bg-[#080810] overflow-hidden">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 bg-transparent" id="webview-area" />
        <InkAide open={aideOpen} onSuccess={() => setAideOk(true)} onClose={() => { setAideOpen(false); setAideOk(false); window.pywebview?.api?.set_aide_width?.(0); }} />
      </div>
    </div>
  );
}
