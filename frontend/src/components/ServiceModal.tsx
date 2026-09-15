import { useState, useRef, useEffect, useMemo } from "react";
import { useAppStore } from "../store";
import type { ServiceEngine } from "../types";

interface Props {
  onClose: () => void;
}

function suggestEngine(url: string): ServiceEngine {
  const raw = url.trim().toLowerCase();
  if (!raw) return "electron";
  let host = raw;
  try {
    const withProto = raw.startsWith("http") ? raw : `https://${raw}`;
    host = new URL(withProto).hostname;
  } catch {
    host = raw.replace(/^https?:\/\//, "").split("/")[0] || raw;
  }
  const googleHints = [
    "google.",
    "youtube.",
    "gmail.",
    "accounts.google",
    "googleapis.",
    "docs.google",
    "drive.google",
    "meet.google",
    "calendar.google",
  ];
  if (googleHints.some((h) => host.includes(h))) return "qt";
  return "electron";
}

function isXDomain(url: string): boolean {
  const raw = url.trim().toLowerCase();
  try {
    const withProto = raw.startsWith("http") ? raw : `https://${raw}`;
    const host = new URL(withProto).hostname.replace(/^www\./, "");
    return host === "x.com" || host === "twitter.com" || host.endsWith(".x.com");
  } catch {
    return /\b(x\.com|twitter\.com)\b/.test(raw);
  }
}

export default function ServiceModal({ onClose }: Props) {
  const { addService, groups } = useAppStore();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [groupId, setGroupId] = useState("");
  const [engine, setEngine] = useState<ServiceEngine>("electron");
  const [engineTouched, setEngineTouched] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!engineTouched) setEngine(suggestEngine(url));
  }, [url, engineTouched]);

  useEffect(() => {
    window.pywebview?.api?.hide_service?.();
    setTimeout(() => nameRef.current?.focus(), 100);
    return () => {
      const activeId = window.__inkBossActiveId;
      if (activeId) window.pywebview?.api?.show_service?.(activeId);
    };
  }, []);

  const xNote = useMemo(() => isXDomain(url), [url]);
  const suggested = useMemo(() => suggestEngine(url), [url]);

  const handleSubmit = async () => {
    if (!name.trim() || !url.trim()) return;
    const normalized = url.startsWith("http") ? url : `https://${url}`;
    await addService(name.trim(), normalized, groupId || undefined, engine);
    onClose();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSubmit();
    if (e.key === "Escape") onClose();
  };

  const filled = !!(name.trim() && url.trim());
  const inputClass =
    "w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/30 transition-colors";

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center"
      style={{ zIndex: 2147483647 }}
    >
      <div className="bg-[#111118] border border-white/10 rounded-2xl w-[26rem] p-6 space-y-5 shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between">
          <h2 className="text-white font-display text-xl tracking-[0.15em]">サービスを追加</h2>
          <button
            onClick={onClose}
            className="text-white/30 hover:text-white/70 transition-colors w-6 h-6 flex items-center justify-center rounded-lg hover:bg-white/5 text-lg leading-none"
          >
            ×
          </button>
        </div>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">
              名前
            </label>
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
            <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">
              URL
            </label>
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="https://discord.com/app"
              className={inputClass}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">
                エンジン
              </label>
              {!engineTouched && url.trim() && (
                <span className="text-[10px] text-white/25 font-mono">
                  おすすめ: {suggested === "qt" ? "Qt" : "Electron"}
                </span>
              )}
            </div>
            <select
              value={engine}
              onChange={(e) => {
                setEngineTouched(true);
                setEngine(e.target.value as ServiceEngine);
              }}
              className="w-full bg-[#111118] border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-white/25 transition-colors"
            >
              <option value="qt">Qt（Googleログイン向け）</option>
              <option value="electron">Electron（メール/パスワードログイン向け）</option>
            </select>
            <p className="text-[11px] leading-relaxed text-white/30 px-0.5">
              「Googleでログイン」が必要な場合はQt、メールアドレス/パスワードでログインする場合はElectronを選んでください。うまくいかない場合は反対のエンジンに切り替えてみてください。
            </p>
            {xNote && (
              <p className="text-[11px] leading-relaxed text-amber-200/50 px-0.5 border-l-2 border-amber-200/20 pl-2">
                Xは自動化検知が特に厳しいため、Electronエンジン＋ユーザー名またはメールアドレスでのログインを推奨します（Googleログインは不安定な場合があります）
              </p>
            )}
          </div>

          {groups.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">
                グループ（任意）
              </label>
              <select
                value={groupId}
                onChange={(e) => setGroupId(e.target.value)}
                className="w-full bg-[#111118] border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-white/25 transition-colors"
              >
                <option value="">グループなし</option>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="flex gap-3 pt-1">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 rounded-xl border border-white/10 text-white/40 hover:text-white/70 hover:bg-white/5 text-sm transition-all"
          >
            キャンセル
          </button>
          <button
            onClick={handleSubmit}
            disabled={!filled}
            className={`flex-1 py-2.5 rounded-xl border text-sm font-medium transition-all ${
              filled
                ? "border-white/40 text-white hover:bg-white/10"
                : "border-white/10 text-white/20 cursor-not-allowed"
            }`}
          >
            追加
          </button>
        </div>
      </div>
    </div>
  );
}
