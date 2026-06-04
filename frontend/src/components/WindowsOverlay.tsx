import { useEffect, useState, useCallback } from "react";
import { useAppStore } from "../store";
import type { Service, Group } from "../types";
import SettingsModal from "./SettingsModal";
import ContextMenu from "./ContextMenu";
import ConfirmDialog from "./ConfirmDialog";

// ── 右クリックペースト対応の入力欄 ────────────────────────
function PasteInput({ value, onChange, placeholder, type = "text", autoFocus = false, className = "" }: {
  value: string; onChange: (v: string) => void;
  placeholder?: string; type?: string;
  autoFocus?: boolean; className?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      autoFocus={autoFocus}
      onChange={(e) => onChange(e.target.value)}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        navigator.clipboard.readText().then((t) => { if (t) onChange(t); }).catch(() => {});
      }}
      placeholder={placeholder}
      className={className}
    />
  );
}

// ── サービス追加ダイアログ ────────────────────────────────
function AddServiceDialog({ defaultGroupId, groups, onClose }: {
  defaultGroupId?: string; groups: Group[]; onClose: () => void;
}) {
  const { addService } = useAppStore();
  const [name, setName] = useState("");
  const [url,  setUrl]  = useState("");
  const [groupId, setGroupId] = useState(defaultGroupId ?? "");
  const inputClass = "w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/30 transition-colors";

  const handleAdd = async () => {
    if (!name.trim() || !url.trim()) return;
    let finalUrl = url.trim();
    if (!/^https?:\/\//i.test(finalUrl)) finalUrl = "https://" + finalUrl;
    await addService(name.trim(), finalUrl, groupId || undefined);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center"
      style={{ zIndex: 2147483647 }} onClick={onClose}>
      <div className="bg-[#111118] border border-white/10 rounded-2xl w-[420px] p-6 space-y-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-white font-display text-xl tracking-[0.15em]">サービスを追加</h2>
          <button onClick={onClose} className="text-white/30 hover:text-white/70 transition-colors w-6 h-6 flex items-center justify-center rounded-lg hover:bg-white/5 text-lg leading-none">×</button>
        </div>
        <div className="space-y-1.5">
          <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">サービス名</label>
          <PasteInput autoFocus value={name} onChange={setName} placeholder="X, Claude, YouTube..." className={inputClass} />
        </div>
        <div className="space-y-1.5">
          <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">URL</label>
          <PasteInput type="url" value={url} onChange={setUrl} placeholder="https://example.com" className={`${inputClass} font-mono text-xs`} />
          <p className="text-[10px] text-white/25">右クリックでクリップボードから貼り付け / Ctrl+V も使用可</p>
        </div>
        {groups.length > 0 && (
          <div className="space-y-1.5">
            <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">グループ（任意）</label>
            <select value={groupId} onChange={(e) => setGroupId(e.target.value)}
              className="w-full bg-[#111118] border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-white/30 transition-colors">
              <option value="">グループなし</option>
              {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
        )}
        <div className="flex gap-3 pt-1">
          <button onClick={onClose}
            className="flex-1 py-2.5 rounded-xl border border-white/10 text-white/40 hover:text-white/70 hover:bg-white/5 text-sm transition-all">キャンセル</button>
          <button onClick={handleAdd} disabled={!name.trim() || !url.trim()}
            className="flex-1 py-2.5 rounded-xl border border-white/40 text-white text-sm font-medium hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all">追加</button>
        </div>
      </div>
    </div>
  );
}

// ── 型定義 ────────────────────────────────────────────────
interface ServiceContextState { x: number; y: number; service: Service; isHib: boolean; }
interface GroupContextState    { x: number; y: number; gid: string; name: string; }
interface AddServiceState      { groupId?: string; }

// ── メインコンポーネント ──────────────────────────────────
export default function WindowsOverlay() {
  const {
    groups, moveService, copyService, hibernateService, wakeService,
    updateService, updateGroup, addGroup, removeGroup,
  } = useAppStore();

  const [serviceMenu,         setServiceMenu]         = useState<ServiceContextState | null>(null);
  const [groupMenu,           setGroupMenu]           = useState<GroupContextState   | null>(null);
  const [showSettings,        setShowSettings]        = useState(false);
  const [showAddService,      setShowAddService]      = useState<AddServiceState | null>(null);
  const [showAddGroup,        setShowAddGroup]        = useState(false);
  const [addGroupName,        setAddGroupName]        = useState("");
  const [confirmDeleteGroup,  setConfirmDeleteGroup]  = useState<{ gid: string; name: string; deleteServices: boolean } | null>(null);
  const [editGroup,           setEditGroup]           = useState<{ id: string; name: string } | null>(null);
  const [editGroupName,       setEditGroupName]       = useState("");
  const [editService,         setEditService]         = useState<{ id: string; name: string; url: string } | null>(null);
  const [editName,            setEditName]            = useState("");
  const [editUrl,             setEditUrl]             = useState("");

  // メニューを閉じる（HWNDはshow_serviceが管理するため、ここでは何もしない）
  const closeAll = useCallback(() => {
    setServiceMenu(null);
    setGroupMenu(null);
  }, []);

  const openEditService = useCallback((svc: Service) => {
    setEditService({ id: svc.id, name: svc.name, url: svc.url ?? "" });
    setEditName(svc.name);
    setEditUrl(svc.url ?? "");
  }, []);

  const removeServiceViaApi = useCallback(async (sid: string) => {
    const api = window.pywebview?.api;
    console.log("[onDelete] calling remove_service:", sid);
    console.log("[onDelete] pywebview api exists:", Boolean(api));
    await api?.remove_service?.(sid);
  }, []);

  useEffect(() => {
    const onContextMenu = (e: CustomEvent) => {
      const { sid, x, y, isHib } = e.detail;
      const svc = useAppStore.getState().services.find((s) => s.id === sid);
      if (!svc) return;
      setGroupMenu(null);
      setServiceMenu({ x, y, service: svc, isHib: Boolean(isHib) });
    };
    const onGroupMenu = (e: CustomEvent) => {
      const { gid, name, x, y } = e.detail;
      setServiceMenu(null);
      setGroupMenu({ gid, name, x, y });
    };
    const onAddService = (e: CustomEvent) => {
      closeAll();
      setShowAddService({ groupId: e.detail || undefined });
    };
    const onAddGroup = () => { closeAll(); setShowAddGroup(true); setAddGroupName(""); };
    const onSettings = () => { closeAll(); setShowSettings(true); };
    window.addEventListener("show-context-menu",       onContextMenu as EventListener);
    window.addEventListener("show-group-context-menu", onGroupMenu   as EventListener);
    window.addEventListener("show-add-service-dialog", onAddService  as EventListener);
    window.addEventListener("show-add-group-dialog",   onAddGroup    as EventListener);
    window.addEventListener("show-settings-dialog",    onSettings    as EventListener);
    return () => {
      window.removeEventListener("show-context-menu",       onContextMenu as EventListener);
      window.removeEventListener("show-group-context-menu", onGroupMenu   as EventListener);
      window.removeEventListener("show-add-service-dialog", onAddService  as EventListener);
      window.removeEventListener("show-add-group-dialog",   onAddGroup    as EventListener);
      window.removeEventListener("show-settings-dialog",    onSettings    as EventListener);
    };
  }, [closeAll]);

  return (
    <>
      {/* 背景クリックでメニューを閉じる */}
      {(serviceMenu || groupMenu) && (
        <div className="fixed inset-0" style={{ zIndex: 2147483646 }}
          onClick={closeAll}
          onContextMenu={(e) => { e.preventDefault(); closeAll(); }} />
      )}

      {/* サービスコンテキストメニュー */}
      {serviceMenu && (
        <ContextMenu
          x={serviceMenu.x} y={serviceMenu.y}
          service={serviceMenu.service} groups={groups}
          isHibernated={serviceMenu.isHib}
          onClose={closeAll}
          onMove={async (gid) => { closeAll(); await moveService(serviceMenu.service.id, gid); }}
          onCopy={async (gid) => { closeAll(); await copyService(serviceMenu.service.id, gid); }}
          onHibernate={async () => { closeAll(); await hibernateService(serviceMenu.service.id); }}
          onWake={async () => { closeAll(); await wakeService(serviceMenu.service.id); }}
          onEdit={() => {
            openEditService(serviceMenu.service);
            closeAll();
          }}
          onDelete={async () => {
            const sid = serviceMenu.service.id;
            closeAll();
            await removeServiceViaApi(sid);
          }}
        />
      )}

      {/* グループコンテキストメニュー */}
      {groupMenu && (
        <div className="fixed bg-[#111118] border border-white/10 rounded-xl shadow-2xl py-1.5 min-w-44"
          style={{ left: groupMenu.x, top: groupMenu.y, zIndex: 2147483647 }}
          onClick={(e) => e.stopPropagation()}>
          <div className="px-3.5 py-1.5 text-[11px] font-mono uppercase tracking-[0.15em] text-white/25 border-b border-white/5 mb-1">
            {groupMenu.name}
          </div>
          <button onClick={() => { closeAll(); window.dispatchEvent(new CustomEvent("show-add-service-dialog", { detail: groupMenu.gid })); }}
            className="w-full text-left px-3.5 py-2 text-sm text-white/60 hover:text-white hover:bg-white/5 transition-colors">
            サービスを追加
          </button>
          <button onClick={() => { setEditGroup({ id: groupMenu.gid, name: groupMenu.name }); setEditGroupName(groupMenu.name); closeAll(); }}
            className="w-full text-left px-3.5 py-2 text-sm text-white/60 hover:text-white hover:bg-white/5 transition-colors">
            名前を変更
          </button>
          <div className="h-px bg-white/5 my-1 mx-2" />
          <button onClick={() => { closeAll(); setConfirmDeleteGroup({ gid: groupMenu.gid, name: groupMenu.name, deleteServices: false }); }}
            className="w-full text-left px-3.5 py-2 text-sm text-red-400/70 hover:text-red-400 hover:bg-red-500/10 transition-colors">
            グループを削除（サービスはグループ解除）
          </button>
          <button onClick={() => { closeAll(); setConfirmDeleteGroup({ gid: groupMenu.gid, name: groupMenu.name, deleteServices: true }); }}
            className="w-full text-left px-3.5 py-2 text-sm text-red-400/70 hover:text-red-400 hover:bg-red-500/10 transition-colors">
            グループとサービスを削除
          </button>
        </div>
      )}

      {/* グループ削除確認 */}
      {confirmDeleteGroup && (
        <ConfirmDialog
          title="グループを削除"
          message={confirmDeleteGroup.deleteServices
            ? `「${confirmDeleteGroup.name}」とその全サービスを削除しますか？`
            : `「${confirmDeleteGroup.name}」を削除しますか？\nサービスはグループ解除されます。`}
          onConfirm={async () => {
            await removeGroup(confirmDeleteGroup.gid, confirmDeleteGroup.deleteServices);
            setConfirmDeleteGroup(null);
          }}
          onCancel={() => setConfirmDeleteGroup(null)}
        />
      )}

      {/* サービス追加 */}
      {showAddService !== null && (
        <AddServiceDialog defaultGroupId={showAddService.groupId} groups={groups} onClose={() => setShowAddService(null)} />
      )}

      {/* グループ追加 */}
      {showAddGroup && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center"
          style={{ zIndex: 2147483647 }} onClick={() => setShowAddGroup(false)}>
          <div className="bg-[#111118] border border-white/10 rounded-2xl w-96 p-6 space-y-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h2 className="text-white font-display text-xl tracking-[0.15em]">グループを追加</h2>
              <button onClick={() => setShowAddGroup(false)} className="text-white/30 hover:text-white/70 w-6 h-6 flex items-center justify-center rounded-lg hover:bg-white/5 text-lg">×</button>
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">グループ名</label>
              <input autoFocus type="text" value={addGroupName} onChange={(e) => setAddGroupName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && addGroupName.trim()) { addGroup(addGroupName.trim()); setShowAddGroup(false); }
                  if (e.key === "Escape") setShowAddGroup(false);
                }}
                placeholder="SNS, AI, ..."
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/30 transition-colors" />
            </div>
            <div className="flex gap-3 pt-1">
              <button onClick={() => setShowAddGroup(false)}
                className="flex-1 py-2.5 rounded-xl border border-white/10 text-white/40 hover:text-white/70 hover:bg-white/5 text-sm transition-all">キャンセル</button>
              <button onClick={() => { if (addGroupName.trim()) { addGroup(addGroupName.trim()); setShowAddGroup(false); } }}
                disabled={!addGroupName.trim()}
                className="flex-1 py-2.5 rounded-xl border border-white/40 text-white text-sm font-medium hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all">作成</button>
            </div>
          </div>
        </div>
      )}

      {/* グループ名変更 */}
      {editGroup && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center"
          style={{ zIndex: 2147483647 }} onClick={() => setEditGroup(null)}>
          <div className="bg-[#111118] border border-white/10 rounded-2xl w-[380px] p-6 space-y-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h2 className="text-white font-display text-xl tracking-[0.15em]">グループ名を変更</h2>
              <button onClick={() => setEditGroup(null)} className="text-white/30 hover:text-white/70 w-6 h-6 flex items-center justify-center rounded-lg hover:bg-white/5 text-lg">×</button>
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">グループ名</label>
              <PasteInput autoFocus value={editGroupName} onChange={setEditGroupName} placeholder={editGroup.name}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/30 transition-colors" />
            </div>
            <div className="flex gap-3 pt-1">
              <button onClick={() => setEditGroup(null)}
                className="flex-1 py-2.5 rounded-xl border border-white/10 text-white/40 hover:text-white/70 hover:bg-white/5 text-sm transition-all">キャンセル</button>
              <button onClick={async () => { if (!editGroupName.trim()) return; await updateGroup(editGroup.id, editGroupName.trim()); setEditGroup(null); }}
                disabled={!editGroupName.trim()}
                className="flex-1 py-2.5 rounded-xl border border-white/40 text-white text-sm font-medium hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all">保存</button>
            </div>
          </div>
        </div>
      )}

      {/* サービス編集 */}
      {editService && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center"
          style={{ zIndex: 2147483647 }} onClick={() => setEditService(null)}>
          <div className="bg-[#111118] border border-white/10 rounded-2xl w-[420px] p-6 space-y-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h2 className="text-white font-display text-xl tracking-[0.15em]">サービスを編集</h2>
              <button onClick={() => setEditService(null)} className="text-white/30 hover:text-white/70 w-6 h-6 flex items-center justify-center rounded-lg hover:bg-white/5 text-lg">×</button>
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">サービス名</label>
              <PasteInput autoFocus value={editName} onChange={setEditName}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/30 transition-colors" />
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">URL</label>
              <PasteInput type="url" value={editUrl} onChange={setEditUrl} placeholder="https://example.com"
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/30 transition-colors font-mono text-xs" />
              <p className="text-[10px] text-white/25">右クリックでクリップボードから貼り付け / Ctrl+V も使用可</p>
            </div>
            <div className="flex gap-3 pt-1">
              <button onClick={() => setEditService(null)}
                className="flex-1 py-2.5 rounded-xl border border-white/10 text-white/40 hover:text-white/70 hover:bg-white/5 text-sm transition-all">キャンセル</button>
              <button onClick={async () => {
                  if (!editName.trim() || !editUrl.trim()) return;
                  let finalUrl = editUrl.trim();
                  if (!/^https?:\/\//i.test(finalUrl)) finalUrl = "https://" + finalUrl;
                  await updateService(editService.id, { name: editName.trim(), url: finalUrl } as any);
                  setEditService(null);
                }}
                disabled={!editName.trim() || !editUrl.trim()}
                className="flex-1 py-2.5 rounded-xl border border-white/40 text-white text-sm font-medium hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all">保存</button>
            </div>
          </div>
        </div>
      )}

      {/* 設定 */}
      {showSettings && (
        <SettingsModal onClose={() => setShowSettings(false)} />
      )}
    </>
  );
}
