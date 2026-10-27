import { create } from "zustand";
import type { Service, Group, AppConfig, LLMConfig, ServiceEngine, Workspace } from "../types";
import { ALL_WORKSPACE_ID } from "../types";

const defaultConfig: AppConfig = {
  version: "2.0.0",
  theme: "dark",
  hibernateMinutes: 10,
  llm: {
    backend: "ollama",
    ollamaUrl: "http://localhost:11434",
    ollamaModel: "qwen2.5:3b",
    claudeApiKey: "",
    geminiApiKey: "",
    deepseekApiKey: "",
  },
  services: [],
  groups: [],
};

/** 開いているワークスペースから見た「サービス一覧」と「グループ一覧」を作る。
 *  「すべて」は従来どおり（services / groups そのまま）。 */
export function deriveView(
  services: Service[],
  groups: Group[],
  workspaces: Workspace[],
  activeId: string,
): { services: Service[]; groups: Group[] } {
  const ws = activeId === ALL_WORKSPACE_ID ? undefined : workspaces.find((w) => w.id === activeId);
  if (!ws) return { services, groups };
  const byId = new Map(services.map((sv) => [sv.id, sv]));
  const view: Service[] = [];
  for (const id of ws.serviceIds) {
    const sv = byId.get(id);
    if (sv) view.push({ ...sv, groupId: ws.groupOf[id] });
  }
  return { services: view, groups: ws.groups };
}

const mapWs = (list: Workspace[], id: string, fn: (w: Workspace) => Workspace) =>
  list.map((w) => (w.id === id ? fn(w) : w));

interface AppStore {
  services: Service[];
  groups: Group[];
  workspaces: Workspace[];
  activeWorkspaceId: string;
  activeServiceId: string | null;
  hibernatedIds: Set<string>;
  wakingIds: Set<string>;
  config: AppConfig;
  loaded: boolean;

  loadConfig: () => Promise<void>;
  setActiveWorkspace: (id: string) => Promise<void>;
  renameWorkspace: (id: string, name: string) => Promise<void>;
  removeWorkspace: (id: string) => Promise<void>;
  /** Python側で処理済みのイベントを反映するだけ（APIは呼ばない） */
  workspaceAddedLocal: (ws: Workspace) => void;
  groupAddedLocal: (g: Group, workspaceId?: string) => void;
  groupRemovedLocal: (gid: string) => void;
  groupRenamedLocal: (gid: string, name: string) => void;
  serviceMovedLocal: (id: string, groupId: string | undefined, workspaceId?: string) => void;
  serviceAddedLocal: (svc: Service, workspaceIds?: string[], wsGroupId?: string | null) => void;
  reorderGroups: (ids: string[]) => Promise<void>;
  serviceWsAddedLocal: (id: string, workspaceId: string) => void;
  serviceWsRemovedLocal: (id: string, workspaceId: string) => void;
  setActiveService: (id: string | null) => void;
  setHibernated: (id: string, val: boolean) => void;
  setWaking: (id: string, val: boolean) => void;

  addService: (name: string, url: string, groupId?: string, engine?: ServiceEngine) => Promise<void>;
  updateService: (id: string, updates: Partial<Service>) => Promise<void>;
  removeService: (id: string) => Promise<void>;
  /** Python 側で既に削除済みのときのローカルのみ更新 */
  dropServiceLocal: (id: string) => void;
  moveService: (id: string, groupId: string) => Promise<void>;
  copyService: (id: string, groupId: string) => Promise<void>;
  hibernateService: (id: string) => Promise<void>;
  wakeService: (id: string) => Promise<void>;
  reorderServices: (ids: string[]) => Promise<void>;

  addGroup: (name: string) => Promise<void>;
  updateGroup: (id: string, name: string) => Promise<void>;
  removeGroup: (id: string, deleteServices: boolean) => Promise<void>;
  toggleGroupCollapsed: (id: string) => void;

  updateLLMConfig: (config: Partial<LLMConfig>) => Promise<void>;
  updateHibernateMinutes: (minutes: number) => Promise<void>;
  exportConfig: () => Promise<string>;
  importConfig: (json: string) => Promise<void>;
}

const api = () => window.pywebview?.api;

export const useAppStore = create<AppStore>((set, get) => ({
  services: [],
  groups: [],
  workspaces: [],
  activeWorkspaceId: ALL_WORKSPACE_ID,
  activeServiceId: null,
  hibernatedIds: new Set(),
  wakingIds: new Set(),
  config: defaultConfig,
  loaded: false,

  loadConfig: async () => {
    // 起動直後は pywebviewready が発火しても js_api 側の準備が
    // 間に合っていないことがある（最初の1回だけ失敗するレース）。
    // 無言で諦めるとサイドバーが永久に空のままになるため、数回リトライする。
    const MAX_ATTEMPTS = 5;
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      try {
        const config = await api().get_config();
        const hibernatedIds = await api().get_hibernated_ids();
        set({
          services: config.services ?? [],
          // 起動時は全グループを折りたたんだ状態で表示する。
          // 開閉状態(collapsed)はconfig.jsonに保存していないため、
          // 以前は作成時の初期値(false=開いた状態)で毎回全グループが
          // 展開されて始まっていた。
          groups: (config.groups ?? []).map((g) => ({ ...g, collapsed: true })),
          workspaces: (config.workspaces ?? []).map((w) => ({
            ...w,
            groups: (w.groups ?? []).map((g) => ({ ...g, collapsed: true })),
          })),
          activeWorkspaceId: config.active_workspace || ALL_WORKSPACE_ID,
          hibernatedIds: new Set(hibernatedIds),
          config: { ...defaultConfig, ...config },
          loaded: true,
        });
        return;
      } catch (e) {
        console.warn(`[loadConfig] attempt ${attempt}/${MAX_ATTEMPTS} failed`, e);
        if (attempt === MAX_ATTEMPTS) {
          set({ loaded: true });
        } else {
          await new Promise((r) => setTimeout(r, 300 * attempt));
        }
      }
    }
  },

  setActiveWorkspace: async (id) => {
    set({ activeWorkspaceId: id });
    try {
      await api().set_active_workspace?.(id);
    } catch (e) {
      console.warn("[setActiveWorkspace]", e);
    }
  },

  renameWorkspace: async (id, name) => {
    const n = name.trim();
    if (!n) return;
    await api().rename_workspace?.(id, n);
    set((s) => ({ workspaces: mapWs(s.workspaces, id, (w) => ({ ...w, name: n })) }));
  },

  removeWorkspace: async (id) => {
    await api().remove_workspace?.(id);
    set((s) => ({
      workspaces: s.workspaces.filter((w) => w.id !== id),
      activeWorkspaceId: s.activeWorkspaceId === id ? ALL_WORKSPACE_ID : s.activeWorkspaceId,
    }));
  },

  workspaceAddedLocal: (ws) =>
    set((s) =>
      s.workspaces.some((w) => w.id === ws.id)
        ? { activeWorkspaceId: ws.id }
        : { workspaces: [...s.workspaces, ws], activeWorkspaceId: ws.id },
    ),

  groupAddedLocal: (g, workspaceId) =>
    set((s) => {
      const grp: Group = { id: g.id, name: g.name, collapsed: g.collapsed ?? false };
      if (workspaceId && workspaceId !== ALL_WORKSPACE_ID) {
        return {
          workspaces: mapWs(s.workspaces, workspaceId, (w) =>
            w.groups.some((x) => x.id === grp.id) ? w : { ...w, groups: [...w.groups, grp] },
          ),
        };
      }
      return s.groups.some((x) => x.id === grp.id) ? s : { groups: [...s.groups, grp] };
    }),

  // グループIDは全体で重複しないので、IDだけで「すべて」とワークスペースの両方から探して消す
  groupRemovedLocal: (gid) =>
    set((s) => ({
      groups: s.groups.filter((g) => g.id !== gid),
      services: s.services.map((sv) => (sv.groupId === gid ? { ...sv, groupId: undefined } : sv)),
      workspaces: s.workspaces.map((w) => ({
        ...w,
        groups: w.groups.filter((g) => g.id !== gid),
        groupOf: Object.fromEntries(Object.entries(w.groupOf).filter(([, g]) => g !== gid)),
      })),
    })),

  groupRenamedLocal: (gid, name) =>
    set((s) => ({
      groups: s.groups.map((g) => (g.id === gid ? { ...g, name } : g)),
      workspaces: s.workspaces.map((w) => ({
        ...w,
        groups: w.groups.map((g) => (g.id === gid ? { ...g, name } : g)),
      })),
    })),

  serviceMovedLocal: (id, groupId, workspaceId) =>
    set((s) => {
      if (workspaceId && workspaceId !== ALL_WORKSPACE_ID) {
        return {
          workspaces: mapWs(s.workspaces, workspaceId, (w) => {
            const groupOf = { ...w.groupOf };
            if (groupId) groupOf[id] = groupId;
            else delete groupOf[id];
            return { ...w, groupOf };
          }),
        };
      }
      return {
        services: s.services.map((sv) => (sv.id === id ? { ...sv, groupId: groupId || undefined } : sv)),
      };
    }),

  serviceAddedLocal: (svc, workspaceIds, wsGroupId) =>
    set((s) => {
      const exists = s.services.some((x) => x.id === svc.id);
      let workspaces = s.workspaces;
      for (const wid of workspaceIds ?? []) {
        workspaces = mapWs(workspaces, wid, (w) => ({
          ...w,
          serviceIds: w.serviceIds.includes(svc.id) ? w.serviceIds : [...w.serviceIds, svc.id],
          groupOf: wsGroupId ? { ...w.groupOf, [svc.id]: wsGroupId } : w.groupOf,
        }));
      }
      return {
        services: exists ? s.services : [...s.services, svc],
        hibernatedIds: exists ? s.hibernatedIds : new Set([...s.hibernatedIds, svc.id]),
        workspaces,
      };
    }),

  serviceWsAddedLocal: (id, workspaceId) =>
    set((s) => ({
      workspaces: mapWs(s.workspaces, workspaceId, (w) =>
        w.serviceIds.includes(id) ? w : { ...w, serviceIds: [...w.serviceIds, id] },
      ),
    })),

  serviceWsRemovedLocal: (id, workspaceId) =>
    set((s) => ({
      workspaces: mapWs(s.workspaces, workspaceId, (w) => ({
        ...w,
        serviceIds: w.serviceIds.filter((x) => x !== id),
        groupOf: Object.fromEntries(Object.entries(w.groupOf).filter(([k]) => k !== id)),
      })),
      activeServiceId:
        s.activeWorkspaceId === workspaceId && s.activeServiceId === id ? null : s.activeServiceId,
    })),

  reorderGroups: async (ids) => {
    const wid = get().activeWorkspaceId;
    set((s) => {
      const sortBy = (gs: Group[]) => {
        const rank = (g: Group) => (ids.includes(g.id) ? ids.indexOf(g.id) : 999);
        return [...gs].sort((a, b) => rank(a) - rank(b));
      };
      if (wid === ALL_WORKSPACE_ID) return { groups: sortBy(s.groups) };
      return { workspaces: mapWs(s.workspaces, wid, (w) => ({ ...w, groups: sortBy(w.groups) })) };
    });
    await api().reorder_groups?.(ids, wid);
  },

  setActiveService: (id) => set({ activeServiceId: id }),
  setHibernated: (id, val) =>
    set((s) => {
      const next = new Set(s.hibernatedIds);
      val ? next.add(id) : next.delete(id);
      return { hibernatedIds: next };
    }),
  setWaking: (id, val) =>
    set((s) => {
      const next = new Set(s.wakingIds);
      val ? next.add(id) : next.delete(id);
      return { wakingIds: next };
    }),

  addService: async (name, url, groupId, engine = "qt") => {
    const wid = get().activeWorkspaceId;
    const service = await api().add_service(name, url, groupId, engine, wid);
    get().serviceAddedLocal(service, wid === ALL_WORKSPACE_ID ? [] : [wid], groupId ?? null);
  },

  updateService: async (id, updates) => {
    await api().update_service(id, updates);
    set((s) => ({
      services: s.services.map((sv) => (sv.id === id ? { ...sv, ...updates } : sv)),
    }));
  },

  removeService: async (id) => {
    await api().remove_service(id);
    get().dropServiceLocal(id);
  },

  dropServiceLocal: (id) => {
    set((s) => ({
      services: s.services.filter((sv) => sv.id !== id),
      workspaces: s.workspaces.map((w) => ({
        ...w,
        serviceIds: w.serviceIds.filter((x) => x !== id),
        groupOf: Object.fromEntries(Object.entries(w.groupOf).filter(([k]) => k !== id)),
      })),
      activeServiceId: s.activeServiceId === id ? null : s.activeServiceId,
    }));
  },

  moveService: async (id, groupId) => {
    const wid = get().activeWorkspaceId;
    await api().move_service(id, groupId, wid);
    get().serviceMovedLocal(id, groupId, wid);
  },

  copyService: async (id, groupId) => {
    const newService = await api().copy_service(id, groupId);
    set((s) => ({
      services: [...s.services, newService],
      hibernatedIds: new Set([...s.hibernatedIds, newService.id]),
    }));
  },

  hibernateService: async (id) => {
    await api().hibernate_service(id);
    set((s) => {
      const next = new Set(s.hibernatedIds);
      next.add(id);
      return {
        hibernatedIds: next,
        activeServiceId: s.activeServiceId === id ? null : s.activeServiceId,
      };
    });
  },

  wakeService: async (id) => {
    get().setWaking(id, true);
    await api().wake_service(id);
    set((s) => {
      const next = new Set(s.hibernatedIds);
      next.delete(id);
      const waking = new Set(s.wakingIds);
      waking.delete(id);
      return { hibernatedIds: next, wakingIds: waking };
    });
  },

  reorderServices: async (ids) => {
    const wid = get().activeWorkspaceId;
    await api().reorder_services?.(ids, wid);
    if (wid !== ALL_WORKSPACE_ID) {
      set((s) => ({
        workspaces: mapWs(s.workspaces, wid, (w) => {
          const mine = new Set(w.serviceIds);
          const head = ids.filter((i) => mine.has(i));
          const seen = new Set(head);
          return { ...w, serviceIds: [...head, ...w.serviceIds.filter((i) => !seen.has(i))] };
        }),
      }));
      return;
    }
    set((s) => {
      const map = new Map(s.services.map((sv) => [sv.id, sv]));
      const ordered: Service[] = [];
      for (const id of ids) {
        const sv = map.get(id);
        if (sv) {
          ordered.push(sv);
          map.delete(id);
        }
      }
      for (const sv of map.values()) ordered.push(sv);
      return { services: ordered };
    });
  },

  addGroup: async (name) => {
    const wid = get().activeWorkspaceId;
    const group = await api().add_group(name, wid);
    get().groupAddedLocal(group, wid);
  },

  updateGroup: async (id, name) => {
    await api().update_group(id, name, get().activeWorkspaceId);
    get().groupRenamedLocal(id, name);
  },

  removeGroup: async (id, deleteServices) => {
    const wid = get().activeWorkspaceId;
    await api().remove_group(id, deleteServices, wid);
    if (wid !== ALL_WORKSPACE_ID) {
      // ワークスペース内: サービス本体は消えず、このワークスペースから外れるだけ
      set((s) => ({
        workspaces: mapWs(s.workspaces, wid, (w) => {
          const members = Object.entries(w.groupOf).filter(([, g]) => g === id).map(([k]) => k);
          return {
            ...w,
            groups: w.groups.filter((g) => g.id !== id),
            serviceIds: deleteServices ? w.serviceIds.filter((x) => !members.includes(x)) : w.serviceIds,
            groupOf: Object.fromEntries(Object.entries(w.groupOf).filter(([, g]) => g !== id)),
          };
        }),
      }));
      return;
    }
    set((s) => ({
      groups: s.groups.filter((g) => g.id !== id),
      services: deleteServices
        ? s.services.filter((sv) => sv.groupId !== id)
        : s.services.map((sv) =>
            sv.groupId === id ? { ...sv, groupId: undefined } : sv,
          ),
    }));
  },

  toggleGroupCollapsed: (id) => {
    set((s) => {
      const flip = (gs: Group[]) => gs.map((g) => (g.id === id ? { ...g, collapsed: !g.collapsed } : g));
      return {
        groups: flip(s.groups),
        workspaces: s.workspaces.map((w) => ({ ...w, groups: flip(w.groups) })),
      };
    });
  },

  updateLLMConfig: async (llmUpdates) => {
    await api().update_llm_config(llmUpdates);
    set((s) => ({ config: { ...s.config, llm: { ...s.config.llm, ...llmUpdates } } }));
  },

  updateHibernateMinutes: async (minutes) => {
    await api().update_hibernate_minutes(minutes);
    set((s) => ({ config: { ...s.config, hibernateMinutes: minutes } }));
  },

  exportConfig: async () => await api().export_config(),

  importConfig: async (json) => {
    await api().import_config(json);
    await get().loadConfig();
  },
}));
