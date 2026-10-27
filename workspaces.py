"""
workspaces.py - ワークスペース（サービスの並びとグループの「ページ」）のデータ操作
Ink Boss / Ink Inc.

【考え方】
- サービス本体（config["services"]）は1か所だけ。ログイン状態も共通。
- ワークスペースは「どのサービスを・どの順で・どのグループで並べるか」を持つだけ。
- 「すべて」(ALL_ID) は仮想のワークスペース。実体は従来の
  config["services"]（順序）/ config["groups"] / service["groupId"] そのもの。
  → 既存の設定は書き換えず、そのまま「すべて」として見える（引き継ぎ処理は不要）。
- このモジュールは「すべて」以外のワークスペースだけを扱う純粋な関数群
  （configのdictを直接更新する。保存は呼び出し側 = api.py が行う）。

ワークスペースの形:
    {
      "id": "ws_xxxxxxxx",
      "name": "SNS",
      "serviceIds": ["service_a", "service_b"],      # 並び順
      "groups": [{"id": "group_x", "name": "...", "collapsed": False}],
      "groupOf": {"service_a": "group_x"}            # サービスID → グループID
    }
"""

import uuid

ALL_ID = "all"


def is_all(wid) -> bool:
    return wid in (None, "", ALL_ID)


def _list(cfg: dict) -> list:
    return cfg.setdefault("workspaces", [])


def find(cfg: dict, wid):
    for w in _list(cfg):
        if w.get("id") == wid:
            return w
    return None


def _service_ids(cfg: dict) -> set:
    return {s.get("id") for s in cfg.get("services", [])}


# ── ワークスペース本体 ────────────────────────────────────
def add_workspace(cfg: dict, name: str) -> dict:
    ws = {
        "id": f"ws_{uuid.uuid4().hex[:8]}",
        "name": (name or "").strip() or "新しいワークスペース",
        "serviceIds": [],
        "groups": [],
        "groupOf": {},
    }
    _list(cfg).append(ws)
    return ws


def rename_workspace(cfg: dict, wid, name: str) -> bool:
    ws = find(cfg, wid)
    name = (name or "").strip()
    if not ws or not name:
        return False
    ws["name"] = name
    return True


def remove_workspace(cfg: dict, wid) -> bool:
    """「すべて」は消せない。サービス本体は消えない（ワークスペースの並びだけ消える）。"""
    if is_all(wid) or not find(cfg, wid):
        return False
    cfg["workspaces"] = [w for w in _list(cfg) if w.get("id") != wid]
    if cfg.get("active_workspace") == wid:
        cfg["active_workspace"] = ALL_ID
    return True


def set_active(cfg: dict, wid) -> bool:
    if is_all(wid):
        cfg["active_workspace"] = ALL_ID
        return True
    if not find(cfg, wid):
        return False
    cfg["active_workspace"] = wid
    return True


# ── サービスの出し入れ ────────────────────────────────────
def add_service(cfg: dict, wid, sid: str, group_id=None) -> bool:
    """ワークスペースへ「複製」（同じサービスを載せるだけ。新しいサービスは作らない）。"""
    ws = find(cfg, wid)
    if not ws or sid not in _service_ids(cfg):
        return False
    if sid not in ws["serviceIds"]:
        ws["serviceIds"].append(sid)
    if group_id and any(g["id"] == group_id for g in ws["groups"]):
        ws["groupOf"][sid] = group_id
    return True


def remove_service(cfg: dict, wid, sid: str) -> bool:
    """このワークスペースからだけ外す（他のワークスペースと「すべて」には残る）。"""
    ws = find(cfg, wid)
    if not ws:
        return False
    ws["serviceIds"] = [x for x in ws["serviceIds"] if x != sid]
    ws["groupOf"].pop(sid, None)
    return True


def purge_service(cfg: dict, sid: str) -> None:
    """サービス本体を削除したとき、全ワークスペースからも取り除く。"""
    for ws in _list(cfg):
        remove_service(cfg, ws["id"], sid)


def reorder_services(cfg: dict, wid, ids) -> bool:
    ws = find(cfg, wid)
    if not ws:
        return False
    order = list(ids or [])
    mine = set(ws["serviceIds"])
    head = [i for i in order if i in mine]
    seen = set(head)
    tail = [i for i in ws["serviceIds"] if i not in seen]
    ws["serviceIds"] = head + tail
    return True


def move_service(cfg: dict, wid, sid: str, gid) -> bool:
    """このワークスペース内でのグループ移動（gid が空ならグループ解除）。"""
    ws = find(cfg, wid)
    if not ws or sid not in ws["serviceIds"]:
        return False
    if not gid:
        ws["groupOf"].pop(sid, None)
        return True
    if not any(g["id"] == gid for g in ws["groups"]):
        return False
    ws["groupOf"][sid] = gid
    return True


# ── グループ（ワークスペースごとに別々） ────────────────────
def add_group(cfg: dict, wid, name: str):
    ws = find(cfg, wid)
    if not ws:
        return None
    g = {"id": f"group_{uuid.uuid4().hex[:8]}", "name": name, "collapsed": False}
    ws["groups"].append(g)
    return g


def update_group(cfg: dict, wid, gid: str, name: str) -> bool:
    ws = find(cfg, wid)
    if not ws:
        return False
    for g in ws["groups"]:
        if g["id"] == gid:
            g["name"] = name
            return True
    return False


def remove_group(cfg: dict, wid, gid: str, delete_services: bool) -> bool:
    """delete_services=True は「このワークスペースから外す」（サービス本体は消さない）。"""
    ws = find(cfg, wid)
    if not ws:
        return False
    ws["groups"] = [g for g in ws["groups"] if g["id"] != gid]
    members = [s for s, g in ws["groupOf"].items() if g == gid]
    for s in members:
        ws["groupOf"].pop(s, None)
        if delete_services:
            ws["serviceIds"] = [x for x in ws["serviceIds"] if x != s]
    return True


def reorder_groups(cfg: dict, wid, ids) -> bool:
    ws = find(cfg, wid)
    if not ws:
        return False
    order = list(ids or [])
    ws["groups"].sort(key=lambda g: order.index(g["id"]) if g["id"] in order else 999)
    return True


# ── 整合性 ─────────────────────────────────────────────
def normalize(cfg: dict) -> bool:
    """設定を読み込んだときに呼ぶ。存在しないサービス/グループへの参照を除き、
    欠けているキーを補う。変更があれば True。"""
    changed = False
    if not isinstance(cfg.get("workspaces"), list):
        cfg["workspaces"] = []
        changed = True
    valid = _service_ids(cfg)
    for ws in cfg["workspaces"]:
        if not isinstance(ws, dict):
            continue
        for key, default in (("serviceIds", []), ("groups", []), ("groupOf", {})):
            if not isinstance(ws.get(key), type(default)):
                ws[key] = type(default)()
                changed = True
        # 重複と存在しないサービスを除く（順序は保つ）
        clean, seen = [], set()
        for sid in ws["serviceIds"]:
            if sid in valid and sid not in seen:
                clean.append(sid)
                seen.add(sid)
        if clean != ws["serviceIds"]:
            ws["serviceIds"] = clean
            changed = True
        gids = {g.get("id") for g in ws["groups"]}
        for sid in list(ws["groupOf"]):
            if sid not in seen or ws["groupOf"][sid] not in gids:
                del ws["groupOf"][sid]
                changed = True
    cfg["workspaces"] = [w for w in cfg["workspaces"] if isinstance(w, dict) and w.get("id")]
    active = cfg.get("active_workspace", ALL_ID)
    if not is_all(active) and not find(cfg, active):
        active = ALL_ID
    if cfg.get("active_workspace") != (ALL_ID if is_all(active) else active):
        cfg["active_workspace"] = ALL_ID if is_all(active) else active
        changed = True
    return changed
