import { useState, useRef, useEffect } from "react";
import { useAppStore } from "../store";
import type { Service } from "../types";
import ConfirmDialog from "./ConfirmDialog";

export default function Sidebar() {
  const {
    services, groups, activeServiceId, hibernatedIds, wakingIds,
    setActiveService, toggleGroupCollapsed,
    moveService, removeService,
    updateGroup, removeGroup, setHibernated,
  } = useAppStore();

  const [expanded, setExpanded] = useState(true);
  const [bottomExpanded, setBottomExpanded] = useState(true);
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const [editingGroupName, setEditingGroupName] = useState("");
  const [confirmDeleteGroupId, setConfirmDeleteGroupId] = useState<string | null>(null);
  const dragService = useRef<string | null>(null);

  useEffect(() => {
    const onHibernated = (e: CustomEvent) => setHibernated(e.detail, true);
    const onWoke = (e: CustomEvent) => setHibernated(e.detail, false);
    const onRemoved = (e: CustomEvent) => removeService(e.detail);
    const onRenamed = (e: CustomEvent) => {
      const { id, name } = e.detail;
      useAppStore.setState((s) => ({ services: s.services.map((sv) => sv.id === id ? { ...sv, name } : sv) }));
    };
    const onAdded = (e: CustomEvent) => {
      const svc = e.detail;
      useAppStore.setState((s) => ({ services: [...s.services, svc], hibernatedIds: new Set([...s.hibernatedIds, svc.id]) }));
    };
    const onGroupAdded = (e: CustomEvent) => {
      useAppStore.setState((s) => ({ groups: [...s.groups, e.detail] }));
    };
    const onGroupRemoved = (e: CustomEvent) => {
      useAppStore.setState((s) => ({
        groups: s.groups.filter((g) => g.id !== e.detail),
        services: s.services.map((sv) => sv.groupId === e.detail ? { ...sv, groupId: undefined } : sv),
      }));
    };
    const onHibChanged = (e: CustomEvent) => {
      useAppStore.setState((s) => ({ config: { ...s.config, hibernateMinutes: e.detail } }));
    };
    const onGroupRenamed = (e: CustomEvent) => {
      const { id, name } = e.detail;
      useAppStore.setState((s) => ({ groups: s.groups.map((g) => g.id === id ? { ...g, name } : g) }));
    };
;
    window.addEventListener("service-hibernated", onHibernated as EventListener);
    window.addEventListener("service-woke", onWoke as EventListener);
    window.addEventListener("service-removed", onRemoved as EventListener);
    window.addEventListener("service-renamed", onRenamed as EventListener);
    window.addEventListener("service-added", onAdded as EventListener);
    window.addEventListener("group-added", onGroupAdded as EventListener);
    window.addEventListener("group-removed", onGroupRemoved as EventListener);
    window.addEventListener("hibernate-changed", onHibChanged as EventListener);
    window.addEventListener("group-renamed", onGroupRenamed as EventListener);
    window.addEventListener("group-renamed", onGroupRenamed as EventListener);
    return () => {
      window.removeEventListener("service-hibernated", onHibernated as EventListener);
      window.removeEventListener("service-woke", onWoke as EventListener);
      window.removeEventListener("service-removed", onRemoved as EventListener);
      window.removeEventListener("service-renamed", onRenamed as EventListener);
      window.removeEventListener("service-added", onAdded as EventListener);
      window.removeEventListener("group-added", onGroupAdded as EventListener);
      window.removeEventListener("group-removed", onGroupRemoved as EventListener);
      window.removeEventListener("hibernate-changed", onHibChanged as EventListener);
      window.removeEventListener("group-renamed", onGroupRenamed as EventListener);
      window.removeEventListener("group-renamed", onGroupRenamed as EventListener);
    };
  }, [setHibernated, removeService]);

  const ungrouped = services.filter((s) => !s.groupId);
  const getFavicon = (url: string) => {
    try { const u = new URL(url); return `https://www.google.com/s2/favicons?domain=${u.hostname}&sz=32`; }
    catch { return null; }
  };
  const handleServiceClick = async (service: Service) => {
    // 休止中はシングルクリック無効（ダブルクリックで復帰）
    if (hibernatedIds.has(service.id) || wakingIds.has(service.id)) return;
    setActiveService(service.id);
    await window.pywebview?.api?.show_service(service.id);
  };
  const handleServiceDoubleClick = async (service: Service) => {
    if (wakingIds.has(service.id)) return;
    // 休止中ならwakeを待ってからsetActiveService
    if (hibernatedIds.has(service.id)) {
      // service-wokeが来たらsetActiveService（一度だけ）
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
  const ServiceItem = ({ service }: { service: Service }) => {
    const isActive = activeServiceId === service.id;
    const isHibernated = hibernatedIds.has(service.id);
    const isWaking = wakingIds.has(service.id);
    const favicon = service.icon || getFavicon(service.url);
    return (
      <button draggable onDragStart={() => { dragService.current = service.id; }}
        onClick={() => handleServiceClick(service)}
        onDoubleClick={() => handleServiceDoubleClick(service)}
        onContextMenu={(e) => {
          e.preventDefault();
          const isHib = hibernatedIds.has(service.id);
          const otherGroups = groups.filter((g) => g.id !== service.groupId);
          const groupsJson = JSON.stringify(otherGroups.map((g) => ({ id: g.id, name: g.name })));
          window.pywebview?.api?.show_context_menu(service.id, service.name, 214, e.clientY, isHib, groupsJson);
        }}
        className={`group relative flex items-center gap-2.5 w-full px-2.5 py-2 rounded-xl transition-all duration-150 select-none ${isHibernated ? "cursor-not-allowed opacity-40" : "cursor-pointer"} ${isActive ? "bg-white/10 border border-white/15" : "hover:bg-white/5 border border-transparent"}`}
        title={!expanded ? (isHibernated ? `${service.name}（ダブルクリックで復帰）` : service.name) : undefined}>
        {isActive && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-5 bg-white/60 rounded-r-full" />}
        <div className="flex-shrink-0 w-7 h-7 rounded-lg overflow-hidden flex items-center justify-center bg-white/5 relative">
          {favicon ? <img src={favicon} alt="" className="w-5 h-5 object-contain" style={{ filter: "grayscale(100%) brightness(1.2)" }} />
            : <span className="text-white/50 text-xs font-bold">{service.name[0]?.toUpperCase()}</span>}
          {isHibernated && !isWaking && <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-lg"><span className="text-white/70 text-[10px]">Z</span></div>}
          {isWaking && <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-lg"><div className="w-3 h-3 border border-white/40 border-t-white/80 rounded-full animate-spin" /></div>}
        </div>
        {expanded && <span className={`text-sm truncate transition-colors ${isActive ? "text-white font-medium" : "text-white/50 group-hover:text-white/80"}`}>{service.name}{isHibernated && !isWaking && <span className="ml-1 text-[10px] text-white/30">休止</span>}</span>}
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
                  window.pywebview?.api?.show_group_context_menu?.(group.id, group.name, e.clientX, e.clientY);
                }}>
                <div className="flex items-center gap-1.5 px-2 py-1 mb-0.5 cursor-grab select-none">
                  <button onClick={(e) => { e.stopPropagation(); toggleGroupCollapsed(group.id); }} className="text-white/20 hover:text-white/50 transition-colors text-[10px] w-3 h-3 flex items-center justify-center flex-shrink-0">{group.collapsed ? "▶" : "▼"}</button>
                  {expanded && <span className="flex-1 text-[10px] font-mono uppercase tracking-[0.15em] text-white/25 truncate">{group.name}</span>}
                </div>
                {!group.collapsed && groupServices.map((s) => <ServiceItem key={s.id} service={s} />)}
              </div>
            );
          })}
          {ungrouped.map((s) => <ServiceItem key={s.id} service={s} />)}
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
