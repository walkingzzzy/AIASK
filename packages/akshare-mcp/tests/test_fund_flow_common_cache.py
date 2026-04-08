from __future__ import annotations


def test_sector_flow_cache_prefers_unified_cache(monkeypatch):
    from akshare_mcp.tools import fund_flow_common as mod

    calls: dict[str, object] = {}

    class _FakeCache:
        def get(self, key, ttl_seconds):
            calls["get"] = (key, ttl_seconds)
            return [{"name": "统一缓存"}]

        def set(self, key, value):
            calls["set"] = (key, value)

    monkeypatch.setattr(mod, "cache", _FakeCache())
    monkeypatch.setattr(mod, "_load_sector_flow_legacy_cache_file", lambda: [{"name": "旧文件"}])

    result = mod._load_sector_flow_cache()

    assert result == [{"name": "统一缓存"}]
    assert calls["get"] == (mod._SECTOR_FLOW_CACHE_KEY, mod._SECTOR_FLOW_CACHE_MAX_AGE)
    assert "set" not in calls


def test_sector_flow_cache_migrates_legacy_file(monkeypatch):
    from akshare_mcp.tools import fund_flow_common as mod

    calls: dict[str, object] = {"sets": []}

    class _FakeCache:
        def get(self, key, ttl_seconds):
            calls["get"] = (key, ttl_seconds)
            return None

        def set(self, key, value):
            calls["sets"].append((key, value))

    monkeypatch.setattr(mod, "cache", _FakeCache())
    monkeypatch.setattr(mod, "_load_sector_flow_legacy_cache_file", lambda: [{"name": "旧文件"}])

    result = mod._load_sector_flow_cache()
    mod._save_sector_flow_cache([{"name": "新数据"}])

    assert result == [{"name": "旧文件"}]
    assert calls["get"] == (mod._SECTOR_FLOW_CACHE_KEY, mod._SECTOR_FLOW_CACHE_MAX_AGE)
    assert calls["sets"] == [
        (mod._SECTOR_FLOW_CACHE_KEY, [{"name": "旧文件"}]),
        (mod._SECTOR_FLOW_CACHE_KEY, [{"name": "新数据"}]),
    ]
