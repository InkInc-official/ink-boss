"""workspaces.py の単体テスト。
実行: python3 tests/test_workspaces.py（pytest があれば pytest tests/ でも可）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import copy
import workspaces as W


def base():
    return {
        "services": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "groups": [{"id": "g_all", "name": "既存"}],
    }


def test_basic_flow():
    c = base()
    s = W.add_workspace(c, "SNS")
    g = W.add_group(c, s["id"], "X")
    assert W.add_service(c, s["id"], "a", g["id"])
    assert W.add_service(c, s["id"], "b")
    assert W.add_service(c, s["id"], "a")  # 重複して入らない
    assert s["serviceIds"] == ["a", "b"]
    assert s["groupOf"] == {"a": g["id"]}
    assert not W.add_service(c, s["id"], "zzz")  # 存在しないサービス
    W.reorder_services(c, s["id"], ["b", "a"])
    assert s["serviceIds"] == ["b", "a"]
    # 並べ替えに載っていないものは末尾に残る
    W.reorder_services(c, s["id"], ["a"])
    assert s["serviceIds"] == ["a", "b"]


def test_copy_does_not_touch_other_workspaces_or_all():
    c = base()
    s1, s2 = W.add_workspace(c, "SNS"), W.add_workspace(c, "配信")
    W.add_service(c, s1["id"], "a")
    W.add_service(c, s2["id"], "a")
    W.remove_service(c, s1["id"], "a")
    assert s1["serviceIds"] == [] and s2["serviceIds"] == ["a"]
    assert [x["id"] for x in c["services"]] == ["a", "b", "c"]  # 本体は残る


def test_groups_are_per_workspace():
    c = base()
    s1, s2 = W.add_workspace(c, "SNS"), W.add_workspace(c, "配信")
    g1 = W.add_group(c, s1["id"], "G1")
    W.add_service(c, s1["id"], "a", g1["id"])
    W.add_service(c, s2["id"], "a")
    assert s2["groupOf"] == {}
    assert not W.move_service(c, s2["id"], "a", g1["id"])  # 他のWSのグループには入れない
    assert W.move_service(c, s1["id"], "a", "")
    assert s1["groupOf"] == {}


def test_remove_group():
    c = base()
    s = W.add_workspace(c, "SNS")
    g = W.add_group(c, s["id"], "G")
    W.add_service(c, s["id"], "a", g["id"])
    W.add_service(c, s["id"], "b", g["id"])
    W.remove_group(c, s["id"], g["id"], False)
    assert s["serviceIds"] == ["a", "b"] and s["groupOf"] == {}
    g = W.add_group(c, s["id"], "G2")
    W.move_service(c, s["id"], "a", g["id"])
    W.remove_group(c, s["id"], g["id"], True)
    assert s["serviceIds"] == ["b"]


def test_remove_workspace_and_active():
    c = base()
    s = W.add_workspace(c, "SNS")
    assert W.set_active(c, s["id"]) and c["active_workspace"] == s["id"]
    assert W.remove_workspace(c, s["id"])
    assert c["active_workspace"] == "all"
    assert not W.remove_workspace(c, "all")
    assert not W.set_active(c, "nope")


def test_purge_service():
    c = base()
    s = W.add_workspace(c, "SNS")
    W.add_service(c, s["id"], "a")
    W.purge_service(c, "a")
    assert s["serviceIds"] == []


def test_rename():
    c = base()
    s = W.add_workspace(c, "SNS")
    assert W.rename_workspace(c, s["id"], " 配信 ") and s["name"] == "配信"
    assert not W.rename_workspace(c, s["id"], "  ")
    assert W.add_workspace(c, "")["name"] == "新しいワークスペース"


def test_normalize_repairs_and_is_idempotent():
    c = base()
    c["workspaces"] = [{"id": "ws_1", "name": "x", "serviceIds": ["a", "a", "gone"],
                        "groups": [{"id": "g1", "name": "g"}],
                        "groupOf": {"a": "g1", "gone": "g1", "b": "g1"}}]
    c["active_workspace"] = "missing"
    assert W.normalize(c)
    ws = c["workspaces"][0]
    assert ws["serviceIds"] == ["a"] and ws["groupOf"] == {"a": "g1"}
    assert c["active_workspace"] == "all"
    before = copy.deepcopy(c)
    assert not W.normalize(c) and c == before


def test_normalize_old_config_without_workspaces():
    c = base()
    assert W.normalize(c)  # 初回: workspaces / active_workspace を補う
    assert c["workspaces"] == [] and c["active_workspace"] == "all"
    assert not W.normalize(c)
    assert [s["id"] for s in c["services"]] == ["a", "b", "c"]  # 既存データは無変更
    assert c["groups"] == [{"id": "g_all", "name": "既存"}]


if __name__ == "__main__":
    n = 0
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            n += 1
            print("ok", _name)
    print(n, "passed")
