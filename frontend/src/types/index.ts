export type ServiceEngine = "qt" | "electron";

export interface Service {
  id: string;
  name: string;
  url: string;
  icon?: string;
  muted: boolean;
  groupId?: string;
  /** 未指定時は "qt"（後方互換） */
  engine?: ServiceEngine;
}

export interface Group {
  id: string;
  name: string;
  collapsed: boolean;
}

/** ワークスペース: サービス本体は共通で、並び順とグループだけを別に持つ「ページ」 */
export interface Workspace {
  id: string;
  name: string;
  serviceIds: string[];
  groups: Group[];
  /** サービスID → グループID */
  groupOf: Record<string, string>;
}

/** 「すべて」（削除・改名できない常設ワークスペース。従来の並び/グループそのもの） */
export const ALL_WORKSPACE_ID = "all";

export type LLMBackend = "ollama" | "claude" | "gemini" | "deepseek";

export interface LLMConfig {
  backend: LLMBackend;
  ollamaUrl: string;
  ollamaModel: string;
  claudeApiKey: string;
  geminiApiKey: string;
  deepseekApiKey: string;
}

export interface AppConfig {
  version: string;
  theme: "dark" | "light";
  hibernateMinutes: number;
  llm: LLMConfig;
  services: Service[];
  groups: Group[];
  workspaces?: Workspace[];
  active_workspace?: string;
}

declare global {
  interface Window {
    pywebview: {
      api: {
        add_service: (
          name: string,
          url: string,
          groupId?: string,
          engine?: ServiceEngine,
          workspaceId?: string,
        ) => Promise<Service>;
        update_service: (id: string, updates: Partial<Service>) => Promise<void>;
        remove_service: (id: string) => Promise<void>;
        move_service: (id: string, groupId: string, workspaceId?: string) => Promise<void>;
        copy_service: (id: string, groupId: string) => Promise<Service>;
        add_group: (name: string, workspaceId?: string) => Promise<Group>;
        update_group: (id: string, name: string, workspaceId?: string) => Promise<void>;
        remove_group: (id: string, deleteServices: boolean, workspaceId?: string) => Promise<void>;
        rename_workspace?: (id: string, name: string) => Promise<boolean>;
        remove_workspace?: (id: string) => Promise<boolean>;
        set_active_workspace?: (id: string) => Promise<boolean>;
        show_add_workspace_dialog?: () => Promise<void>;
        get_config: () => Promise<AppConfig>;
        export_config: () => Promise<string>;
        import_config: (json: string) => Promise<void>;
        update_llm_config: (config: Partial<LLMConfig>) => Promise<void>;
        update_hibernate_minutes: (minutes: number) => Promise<void>;
        show_service: (id: string) => Promise<void>;
        hide_service?: () => Promise<void>;
        reload_service: (id: string) => Promise<void>;
        hibernate_service: (id: string) => Promise<void>;
        wake_service: (id: string) => Promise<void>;
        get_hibernated_ids: () => Promise<string[]>;
        reorder_groups?: (ids: string[], workspaceId?: string) => Promise<void>;
        reorder_services?: (ids: string[], workspaceId?: string) => Promise<void>;
        show_context_menu?: (
          id: string,
          name: string,
          x: number,
          y: number,
          isHib: boolean,
          groupsJson: string,
        ) => Promise<void>;
        show_group_context_menu?: (
          id: string,
          name: string,
          x: number,
          y: number,
        ) => Promise<void>;
        show_add_service_dialog?: (groupId?: string) => Promise<void>;
        show_add_group_dialog?: () => Promise<void>;
        show_settings_dialog?: () => Promise<void>;
        close_window?: () => Promise<void>;
        minimize_window?: () => Promise<void>;
        toggle_maximize?: () => Promise<void>;
        update_title?: (title: string) => Promise<void>;
        set_aide_width?: (width: number) => Promise<void>;
        drag_start?: () => Promise<void>;
        drag_end?: () => Promise<void>;
        sync_geometry?: (id: string) => Promise<void>;
        get_page_text?: (id: string) => Promise<string>;
      };
    };
    __inkBossActiveId: string | null;
  }
}

export {};
