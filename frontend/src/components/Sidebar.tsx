import { useState, useRef, useEffect, useCallback } from "react";
import { useAppStore } from "../store";
import type { Service } from "../types";
import ConfirmDialog from "./ConfirmDialog";

export default function Sidebar() {
  const {
    services, groups, activeServiceId, hibernatedIds, wakingIds,
    setActiveService, toggleGroupCollapsed,
    moveService, dropServiceLocal, reorderServices,
    removeGroup, setHibernated, updateService,
  } = useAppStore();

  const [expanded, setExpanded] = useState(true);
  const [bottomExpanded, setBottomExpanded] = useState(true);
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const [editingGroupName, setEditingGroupName] = useState("");
  const [confirmDeleteGroupId, setConfirmDeleteGroupId] = useState<string | null>(null);
  const dragService = useRef<string | null>(null);
  const dragSourceGroup = useRef<string | undefined>(undefined);

  useEffect(() => {
    const onHibernated = (e: CustomEvent) => setHibernated(e.detail, true);
    const onWoke = (e: CustomEvent) => setHibernated(e.detail, false);
    // Python 側で既に config/view 削除済み → API 再呼び出し禁止
    const onRemoved = (e: CustomEvent) => dropServiceLocal(e.detail);
    const onRenamed = (e: CustomEvent) => {
      const { id, name } = e.detail;
      useAppStore.setState((s) => ({
        services: s.services.map((sv) => (sv.id === id ? { ...sv, name } : sv)),
      }));
    };
    const onIcon = (e: CustomEvent) => {
      const { id, icon } = e.detail;
      useAppStore.setState((s) => ({
        services: s.services.map((sv) => (sv.id === id ? { ...sv, icon } : sv)),
      }));
    };
    const onUrlChanged = (e: CustomEvent) => {
      const { id, url } = e.detail;
      useAppStore.setState((s) => ({
        services: s.services.map((sv) => (sv.id === id ? { ...sv, url } : sv)),
      }));
    };
    const onEngine = (e: CustomEvent) => {
      const { id, engine } = e.detail;
      void updateService(id, { engine });
    };
    const onAdded = (e: CustomEvent) => {
      const svc = e.detail;
      useAppStore.setState((s) => {
        if (s.services.some((x) => x.id === svc.id)) return s;
        return {
          services: [...s.services, svc],
          hibernatedIds: new Set([...s.hibernatedIds, svc.id]),
        };
      });
    };
    const onGroupAdded = (e: CustomEvent) => {
      useAppStore.setState((s) => ({ groups: [...s.groups, e.detail] }));
    };
    const onGroupRemoved = (e: CustomEvent) => {
      useAppStore.setState((s) => ({
        groups: s.groups.filter((g) => g.id !== e.detail),
        services: s.services.map((sv) =>
          sv.groupId === e.detail ? { ...sv, groupId: undefined } : sv,
        ),
      }));
    };
    const onHibChanged = (e: CustomEvent) => {
      useAppStore.setState((s) => ({
        config: { ...s.config, hibernateMinutes: e.detail },
      }));
    };
    const onGroupRenamed = (e: CustomEvent) => {
      const { id, name } = e.detail;
      useAppStore.setState((s) => ({
        groups: s.groups.map((g) => (g.id === id ? { ...g, name } : g)),
      }));
    };

    const pairs: [string, EventListener][] = [
      ["service-hibernated", onHibernated as EventListener],
      ["service-woke", onWoke as EventListener],
      ["service-removed", onRemoved as EventListener],
      ["service-renamed", onRenamed as EventListener],
      ["service-icon-changed", onIcon as EventListener],
      ["service-url-changed", onUrlChanged as EventListener],
      ["service-engine-changed", onEngine as EventListener],
      ["service-added", onAdded as EventListener],
      ["group-added", onGroupAdded as EventListener],
      ["group-removed", onGroupRemoved as EventListener],
      ["hibernate-changed", onHibChanged as EventListener],
      ["group-renamed", onGroupRenamed as EventListener],
    ];
    for (const [n, h] of pairs) window.addEventListener(n, h);
    return () => {
      for (const [n, h] of pairs) window.removeEventListener(n, h);
    };
  }, [setHibernated, dropServiceLocal, updateService]);

  const ungrouped = services.filter((s) => !s.groupId);
  const getFavicon = (url: string) => {
    try { const u = new URL(url); return `https://www.google.com/s2/favicons?domain=${u.hostname}&sz=32`; }
    catch { return null; }
  };
  const handleServiceClick = async (service: Service) => {
    if (hibernatedIds.has(service.id) || wakingIds.has(service.id)) return;
    setActiveService(service.id);
    await window.pywebview?.api?.show_service(service.id);
  };
  const handleServiceDoubleClick = async (service: Service) => {
    if (wakingIds.has(service.id)) return;
    if (hibernatedIds.has(service.id)) {
      const onWoke = (e: CustomEvent) => {
        if (e.detail === service.id) {
          setActiveService(service.id);
          window.removeEventListener("service-woke", onWoke as EventListener);
        }
      };
      window.addEventListener("service-woke", onWoke as EventListener);
      await window.pywebview?.api?.show_service(service.id);
      return;
    }
    setActiveService(service.id);
    await window.pywebview?.api?.show_service(service.id);
  };

  // ── サービスDnD並べ替え ──────────────────────────────
  const handleServiceDragStart = useCallback((serviceId: string, groupId: string | undefined) => {
    dragService.current = serviceId;
    dragSourceGroup.current = groupId;
  }, []);

  const handleServiceDrop = useCallback(async (
    targetServiceId: string,
    targetGroupId: string | undefined,
  ) => {
    const srcId = dragService.current;
    if (!srcId) return;
    dragService.current = null;

    // 自分自身にドロップ → 何もしない
    if (srcId === targetServiceId) return;

    const srcGroup = dragSourceGroup.current;
    dragSourceGroup.current = undefined;

    // 異なるグループ間の移動 → moveService を使う
    if (srcGroup !== targetGroupId) {
      await moveService(srcId, targetGroupId ?? "");
      return;
    }

    // 同じグループ内の並べ替え
    const sameGroupServices = services.filter((s) => s.groupId === targetGroupId);
    const ids = sameGroupServices.map((s) => s.id);
    const fromIdx = ids.indexOf(srcId);
    const toIdx = ids.indexOf(targetServiceId);
    if (fromIdx === -1 || toIdx === -1) return;

    // 配列を並べ替え
    ids.splice(fromIdx, 1);
    ids.splice(toIdx, 0, srcId);
    await reorderServices(ids);
  }, [services, moveService, reorderServices]);

  const ServiceItem = ({ service, groupId }: { service: Service; groupId?: string }) => {
    const isActive = activeServiceId === service.id;
    const isHibernated = hibernatedIds.has(service.id);
    const isWaking = wakingIds.has(service.id);
    const favicon = service.icon || getFavicon(service.url);
    const eng = service.engine === "electron" ? "E" : "Q";
    return (
      <button draggable
        onDragStart={() => handleServiceDragStart(service.id, groupId ?? service.groupId)}
        onDragOver={(e) => { e.preventDefault(); }}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          handleServiceDrop(service.id, groupId ?? service.groupId);
        }}
        onClick={() => handleServiceClick(service)}
        onDoubleClick={() => handleServiceDoubleClick(service)}
        onContextMenu={(e) => {
          e.preventDefault();
          const isHib = hibernatedIds.has(service.id);
          const otherGroups = groups.filter((g) => g.id !== service.groupId);
          const groupsJson = JSON.stringify(otherGroups.map((g) => ({ id: g.id, name: g.name })));
          // スクリーン絶対座標（Qt QMenu は screen 座標）
          const sx = Math.round((window.screenX || 0) + e.clientX);
          const sy = Math.round((window.screenY || 0) + e.clientY);
          window.pywebview?.api?.show_context_menu?.(
            service.id, service.name, sx, sy, isHib, groupsJson,
          );
        }}
        className={`group relative flex items-center gap-2.5 w-full px-2.5 py-2 rounded-xl transition-all duration-150 select-none ${isHibernated ? "cursor-not-allowed opacity-40" : "cursor-pointer"} ${isActive ? "bg-white/10 border border-white/15" : "hover:bg-white/5 border border-transparent"}`}
        title={!expanded ? (isHibernated ? `${service.name}（ダブルクリックで復帰）` : service.name) : undefined}>
        {isActive && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-5 bg-white/60 rounded-r-full" />}
        <div className="flex-shrink-0 w-7 h-7 rounded-lg overflow-hidden flex items-center justify-center bg-white/5 relative">
          {favicon ? (
            <img
              src={favicon}
              alt=""
              className="w-5 h-5 object-contain"
              // 色付きファビコン（以前の grayscale をやめる）
              onError={(ev) => {
                (ev.target as HTMLImageElement).style.display = "none";
              }}
            />
          ) : (
            <span className="text-white/50 text-xs font-bold">{service.name[0]?.toUpperCase()}</span>
          )}
          {isHibernated && !isWaking && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-lg">
              <span className="text-white/70 text-[10px]">Z</span>
            </div>
          )}
          {isWaking && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-lg">
              <div className="w-3 h-3 border border-white/40 border-t-white/80 rounded-full animate-spin" />
            </div>
          )}
        </div>
        {expanded && (
          <span
            className={`flex-1 text-sm truncate transition-colors ${
              isActive ? "text-white font-medium" : "text-white/50 group-hover:text-white/80"
            }`}
          >
            {service.name}
            {isHibernated && !isWaking && (
              <span className="ml-1 text-[10px] text-white/30">休止</span>
            )}
          </span>
        )}
        {expanded && (
          <span
            className={`text-[9px] font-mono flex-shrink-0 px-1 py-0.5 rounded ${
              eng === "E" ? "text-sky-300/70 bg-sky-400/10" : "text-white/25 bg-white/5"
            }`}
            title={eng === "E" ? "Electron" : "Qt"}
          >
            {eng}
          </span>
        )}
      </button>
    );
  };
  const confirmDeleteGroup = groups.find((g) => g.id === confirmDeleteGroupId);
  return (
    <>
      <aside className={`flex flex-col h-full transition-all duration-200 bg-[#0a0a12] border-r border-white/5 ${expanded ? "w-52" : "w-[52px]"}`}>
        <div className="flex items-center h-14 px-3 border-b border-white/5 cursor-pointer flex-shrink-0 gap-3" onClick={() => setExpanded(!expanded)}>
          <div className="flex-shrink-0 w-7 h-7 flex items-center justify-center overflow-hidden">
            <img src="/icon.png" alt="IB" className="w-7 h-7 object-cover rounded-lg" style={{ filter: "grayscale(100%) brightness(1.4)" }} onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
          </div>
          {expanded && <span className="text-white font-display text-lg tracking-[0.2em] leading-none">INK BOSS</span>}
        </div>
        <nav className="flex-1 overflow-y-auto overflow-x-hidden px-1.5 py-3 space-y-0.5 scrollbar-thin">
          {groups.map((group) => {
            const groupServices = services.filter((s) => s.groupId === group.id);
            return (
              <div key={group.id}
                draggable
                onDragStart={(e) => { dragService.current = null; e.dataTransfer.setData("dragGroupId", group.id); }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  const srcId = e.dataTransfer.getData("dragGroupId");
                  if (srcId && srcId !== group.id) {
                    useAppStore.setState((s) => {
                      const gs = [...s.groups];
                      const from = gs.findIndex((g: any) => g.id === srcId);
                      const to = gs.findIndex((g: any) => g.id === group.id);
                      if (from !== -1 && to !== -1) { const [item] = gs.splice(from, 1); gs.splice(to, 0, item); }
                      return { groups: gs };
                    });
                    window.pywebview?.api?.reorder_groups?.(useAppStore.getState().groups.map((g: any) => g.id));
                  } else if (dragService.current) {
                    moveService(dragService.current, group.id);
                    dragService.current = null;
                  }
                }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  const sx = Math.round((window.screenX || 0) + e.clientX);
                  const sy = Math.round((window.screenY || 0) + e.clientY);
                  window.pywebview?.api?.show_group_context_menu?.(
                    group.id, group.name, sx, sy,
                  );
                }}>
                <div className="flex items-center gap-1.5 px-2 py-1 mb-0.5 cursor-grab select-none">
                  <button onClick={(e) => { e.stopPropagation(); toggleGroupCollapsed(group.id); }} className="text-white/20 hover:text-white/50 transition-colors text-[10px] w-3 h-3 flex items-center justify-center flex-shrink-0">{group.collapsed ? "▶" : "▼"}</button>
                  {expanded && <span className="flex-1 text-[10px] font-mono uppercase tracking-[0.15em] text-white/25 truncate">{group.name}</span>}
                </div>
                {!group.collapsed && groupServices.map((s) => <ServiceItem key={s.id} service={s} groupId={group.id} />)}
              </div>
            );
          })}
          {/* 未分類サービスの見出し。
              グループが1つ以上ある状態でこれが無いと、新規グループの
              直後に未分類サービスが続くため、そのグループに属している
              ように見えてしまう（データ上は正しくても視覚的に誤解される）。 */}
          {groups.length > 0 && ungrouped.length > 0 && (
            <div className="flex items-center gap-1.5 px-2 py-1 mb-0.5 mt-2 pt-2 border-t border-white/5 select-none">
              {expanded && <span className="flex-1 text-[10px] font-mono uppercase tracking-[0.15em] text-white/25 truncate">未分類</span>}
            </div>
          )}
          {/* 未分類サービス → ドロップゾーンとしても機能 */}
          <div onDragOver={(e) => e.preventDefault()}
               onDrop={(e) => {
                 e.preventDefault();
                 const srcId = dragService.current;
                 if (srcId) {
                   const svc = services.find((s) => s.id === srcId);
                   if (svc && svc.groupId) {
                     moveService(srcId, "");
                     dragService.current = null;
                   } else if (svc && !svc.groupId) {
                     // 未分類同士の並べ替え
                     const ungroupedIds = services.filter((s) => !s.groupId).map((s) => s.id);
                     const fromIdx = ungroupedIds.indexOf(srcId);
                     if (fromIdx !== -1) {
                       ungroupedIds.splice(fromIdx, 1);
                       ungroupedIds.push(srcId);
                       reorderServices(ungroupedIds);
                     }
                     dragService.current = null;
                   }
                 }
               }}>
            {ungrouped.map((s) => <ServiceItem key={s.id} service={s} />)}
          </div>
        </nav>
        <div className="h-px bg-white/5 mx-3" />
        <div className="flex-shrink-0 px-1.5 py-2">
          <button onClick={() => setBottomExpanded(!bottomExpanded)} className="flex items-center justify-center w-full py-1 text-white/20 hover:text-white/50 transition-colors text-xs">
            {bottomExpanded ? "▽" : "△"}
          </button>
          {bottomExpanded && (
            <div className="space-y-0.5 mt-1">
              <button onClick={() => window.pywebview?.api?.show_add_service_dialog()} className="flex items-center gap-2.5 w-full px-2.5 py-2 rounded-xl text-white/40 hover:text-white/80 hover:bg-white/5 transition-all" title={!expanded ? "サービスを追加" : undefined}>
                <span className="flex-shrink-0 w-7 h-7 flex items-center justify-center text-lg leading-none font-light">+</span>
                {expanded && <span className="text-sm">追加</span>}
              </button>
              <button onClick={() => window.pywebview?.api?.show_add_group_dialog()} className="flex items-center gap-2.5 w-full px-2.5 py-2 rounded-xl text-white/40 hover:text-white/80 hover:bg-white/5 transition-all" title={!expanded ? "グループを追加" : undefined}>
                <span className="flex-shrink-0 w-7 h-7 flex items-center justify-center text-lg leading-none font-light">G</span>
                {expanded && <span className="text-sm">グループ</span>}
              </button>
              <button onClick={() => window.pywebview?.api?.show_settings_dialog()} className="flex items-center gap-2.5 w-full px-2.5 py-2 rounded-xl text-white/40 hover:text-white/80 hover:bg-white/5 transition-all" title={!expanded ? "設定" : undefined}>
                <span className="flex-shrink-0 w-7 h-7 flex items-center justify-center">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                </span>
                {expanded && <span className="text-sm">設定</span>}
              </button>
            </div>
          )}
        </div>
      </aside>
      {confirmDeleteGroupId && confirmDeleteGroup && (
        <ConfirmDialog title="グループを削除" message={`「${confirmDeleteGroup.name}」を削除しますか？\nサービスはグループ解除されます。`}
          onConfirm={() => { removeGroup(confirmDeleteGroupId, false); setConfirmDeleteGroupId(null); }}
          onCancel={() => setConfirmDeleteGroupId(null)} />
      )}
    </>
  );
}