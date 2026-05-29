import { useState } from "react";
import { useAppStore } from "../store";
import type { LLMBackend } from "../types";

interface Props { onClose: () => void; }

export default function SettingsModal({ onClose }: Props) {
  const { config, updateLLMConfig, updateHibernateMinutes, exportConfig, importConfig, addGroup, groups } = useAppStore();
  const [tab, setTab] = useState<"general" | "llm" | "groups" | "data">("general");
  const [newGroupName, setNewGroupName] = useState("");
  const [importText, setImportText] = useState("");
  const [confirmDeleteGroupId, setConfirmDeleteGroupId] = useState<string | null>(null);
  const { removeGroup } = useAppStore();
  const llm = config.llm;

  const backends: { value: LLMBackend; label: string; desc: string }[] = [
    { value: "ollama", label: "Ollama", desc: "ローカルLLM・無料・完全オフライン" },
    { value: "claude", label: "Claude API", desc: "高精度・従量課金・要APIキー" },
    { value: "gemini", label: "Gemini API", desc: "無料枠あり・取得容易・要APIキー" },
  ];

  const hibernateOptions = [
    { value: 0, label: "無効" },
    { value: 5, label: "5分" },
    { value: 10, label: "10分" },
    { value: 15, label: "15分" },
    { value: 30, label: "30分" },
    { value: 60, label: "1時間" },
  ];

  const handleExport = async () => {
    const json = await exportConfig();
    const blob = new Blob([json], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "ink-boss-config.json";
    a.click();
  };

  const handleImport = async () => {
    if (!importText.trim()) return;
    await importConfig(importText);
    setImportText("");
    onClose();
  };

  const inputClass = "w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/25 transition-colors font-mono";

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center" style={{ zIndex: 2147483647 }}>
      <div className="bg-[#111118] border border-white/10 rounded-2xl w-[520px] h-[520px] flex flex-col shadow-2xl shadow-black/60 overflow-hidden">

        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 flex-shrink-0">
          <h2 className="font-display text-xl tracking-[0.15em] text-white">設定</h2>
          <button onClick={onClose} className="text-white/30 hover:text-white/70 transition-colors w-6 h-6 flex items-center justify-center rounded-lg hover:bg-white/5 text-lg leading-none">×</button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          <nav className="w-36 border-r border-white/5 flex-shrink-0 py-3 space-y-0.5 px-2">
            {(["general", "llm", "groups", "data"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`w-full text-left px-3 py-2 rounded-xl text-sm transition-all ${
                  tab === t ? "bg-white/10 text-white border border-white/15" : "text-white/40 hover:text-white/70 hover:bg-white/5"
                }`}>
                {{ general: "一般", llm: "AI / LLM", groups: "グループ", data: "データ" }[t]}
              </button>
            ))}
          </nav>

          <div className="flex-1 overflow-y-auto p-5 space-y-4">

            {/* General */}
            {tab === "general" && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">休止モード</p>
                  <p className="text-xs text-white/30 leading-relaxed">
                    非アクティブなサービスを指定時間後に自動休止してメモリを解放します
                  </p>
                  <div className="grid grid-cols-3 gap-2">
                    {hibernateOptions.map((opt) => (
                      <button key={opt.value}
                        onClick={() => updateHibernateMinutes(opt.value)}
                        className={`py-2 rounded-xl border text-sm transition-all ${
                          config.hibernateMinutes === opt.value
                            ? "border-white/30 bg-white/10 text-white"
                            : "border-white/8 text-white/40 hover:border-white/20 hover:text-white/70"
                        }`}>
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* LLM */}
            {tab === "llm" && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">バックエンド</p>
                  {backends.map((b) => (
                    <label key={b.value} className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                      llm.backend === b.value ? "border-white/25 bg-white/5" : "border-white/8 hover:border-white/15"
                    }`}>
                      <input type="radio" name="backend" value={b.value} checked={llm.backend === b.value}
                        onChange={() => updateLLMConfig({ backend: b.value })} className="mt-0.5 accent-white" />
                      <div>
                        <p className="text-sm text-white">{b.label}</p>
                        <p className="text-xs text-white/40 mt-0.5">{b.desc}</p>
                      </div>
                    </label>
                  ))}
                </div>
                {llm.backend === "ollama" && (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">OllamaサーバーURL</label>
                      <input type="text" value={llm.ollamaUrl} onChange={(e) => updateLLMConfig({ ollamaUrl: e.target.value })} className={inputClass} />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">モデル名</label>
                      <input type="text" value={llm.ollamaModel} onChange={(e) => updateLLMConfig({ ollamaModel: e.target.value })} placeholder="llama3" className={inputClass} />
                    </div>
                  </div>
                )}
                {llm.backend === "claude" && (
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">Claude APIキー</label>
                    <input type="password" value={llm.claudeApiKey} onChange={(e) => updateLLMConfig({ claudeApiKey: e.target.value })} placeholder="sk-ant-..." className={inputClass} />
                  </div>
                )}
                {llm.backend === "gemini" && (
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">Gemini APIキー</label>
                    <input type="password" value={llm.geminiApiKey} onChange={(e) => updateLLMConfig({ geminiApiKey: e.target.value })} placeholder="AIza..." className={inputClass} />
                  </div>
                )}
              </div>
            )}

            {/* Groups */}
            {tab === "groups" && (
              <div className="space-y-4">
                <div className="flex gap-2">
                  <input type="text" value={newGroupName} onChange={(e) => setNewGroupName(e.target.value)}
                    placeholder="グループ名"
                    className="flex-1 bg-white/5 border border-white/10 rounded-xl px-3.5 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/25 transition-colors"
                    onKeyDown={(e) => { if (e.key === "Enter" && newGroupName.trim()) { addGroup(newGroupName.trim()); setNewGroupName(""); } }}
                  />
                  <button onClick={() => { if (newGroupName.trim()) { addGroup(newGroupName.trim()); setNewGroupName(""); } }}
                    className="px-4 py-2 border border-white/15 text-white/70 rounded-xl text-sm hover:bg-white/5 hover:text-white transition-all">
                    追加
                  </button>
                </div>
                <div className="space-y-1.5">
                  {groups.length === 0 && <p className="text-sm text-white/30">グループがありません</p>}
                  {groups.map((g) => (
                    <div key={g.id} className="flex items-center justify-between px-3.5 py-2.5 bg-white/5 rounded-xl border border-white/8">
                      <span className="text-sm text-white/70">{g.name}</span>
                      <button onClick={() => setConfirmDeleteGroupId(g.id)}
                        className="text-white/25 hover:text-white/70 transition-colors text-xs px-2 py-1 rounded-lg hover:bg-white/5">
                        削除
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Data */}
            {tab === "data" && (
              <div className="space-y-4">
                <button onClick={handleExport}
                  className="w-full py-2.5 rounded-xl border border-white/15 text-white/60 text-sm hover:bg-white/5 hover:text-white transition-all">
                  設定をエクスポート（JSON）
                </button>
                <div className="space-y-2">
                  <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">設定をインポート</p>
                  <textarea value={importText} onChange={(e) => setImportText(e.target.value)}
                    placeholder="JSONを貼り付け..." rows={5}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2 text-xs font-mono text-white placeholder-white/20 focus:outline-none focus:border-white/25 resize-none transition-colors" />
                  <button onClick={handleImport} disabled={!importText.trim()}
                    className="w-full py-2.5 rounded-xl border border-white/15 text-white/60 text-sm hover:bg-white/5 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                    インポート
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {confirmDeleteGroupId && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[60]">
          <div className="bg-[#111118] border border-white/10 rounded-2xl w-80 p-6 space-y-5 shadow-2xl">
            <div className="space-y-1.5">
              <h3 className="text-white font-display text-lg tracking-[0.1em]">グループを削除</h3>
              <p className="text-sm text-white/45 leading-relaxed">このグループを削除しますか？<br />サービスはグループ解除されます。</p>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setConfirmDeleteGroupId(null)}
                className="flex-1 py-2.5 rounded-xl border border-white/10 text-white/40 hover:text-white/70 hover:bg-white/5 text-sm transition-all">
                キャンセル
              </button>
              <button onClick={() => { removeGroup(confirmDeleteGroupId, false); setConfirmDeleteGroupId(null); }}
                className="flex-1 py-2.5 rounded-xl border border-white/25 text-white/80 hover:bg-white/10 hover:text-white text-sm transition-all">
                削除する
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
