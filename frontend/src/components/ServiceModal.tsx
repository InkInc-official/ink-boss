import { useState, useRef, useEffect } from "react";
import { useAppStore } from "../store";

interface Props { onClose: () => void; }

export default function ServiceModal({ onClose }: Props) {
  const { addService, groups } = useAppStore();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [groupId, setGroupId] = useState("");
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // モーダル表示時にWebViewを一時的に後ろに送る
    window.pywebview?.api?.hide_service?.();
    setTimeout(() => nameRef.current?.focus(), 100);
    return () => {
      // モーダルを閉じたときにWebViewを戻す
      const activeId = window.__inkBossActiveId;
      if (activeId) window.pywebview?.api?.show_service?.(activeId);
    };
  }, []);

  const handleSubmit = async () => {
    if (!name.trim() || !url.trim()) return;
    const normalized = url.startsWith("http") ? url : `https://${url}`;
    await addService(name.trim(), normalized, groupId || undefined);
    onClose();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSubmit();
    if (e.key === "Escape") onClose();
  };

  const filled = name.trim() && url.trim();

  const inputClass = "w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/30 transition-colors";

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center"
      style={{ zIndex: 2147483647 }}
    >
      <div className="bg-[#111118] border border-white/10 rounded-2xl w-96 p-6 space-y-5 shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between">
          <h2 className="text-white font-display text-xl tracking-[0.15em]">サービスを追加</h2>
          <button onClick={onClose} className="text-white/30 hover:text-white/70 transition-colors w-6 h-6 flex items-center justify-center rounded-lg hover:bg-white/5 text-lg leading-none">×</button>
        </div>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">名前</label>
            <input
              ref={nameRef}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Discord"
              className={inputClass}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">URL</label>
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="https://discord.com/app"
              className={inputClass}
            />
          </div>
          {groups.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">グループ（任意）</label>
              <select value={groupId} onChange={(e) => setGroupId(e.target.value)}
                className="w-full bg-[#111118] border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-white/25 transition-colors">
                <option value="">グループなし</option>
                {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            </div>
          )}
        </div>

        <div className="flex gap-3 pt-1">
          <button onClick={onClose}
            className="flex-1 py-2.5 rounded-xl border border-white/10 text-white/40 hover:text-white/70 hover:bg-white/5 text-sm transition-all">
            キャンセル
          </button>
          <button onClick={handleSubmit} disabled={!filled}
            className={`flex-1 py-2.5 rounded-xl border text-sm font-medium transition-all ${
              filled
                ? "border-white/40 text-white hover:bg-white/10"
                : "border-white/10 text-white/20 cursor-not-allowed"
            }`}>
            追加
          </button>
        </div>
      </div>
    </div>
  );
}
