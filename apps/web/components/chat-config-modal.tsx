'use client';

import { useEffect, useState } from 'react';
import { getLlmConfig, saveLlmConfig, getModelPresets, type ModelPreset } from '@/lib/chat-api';
import { useChatStore } from '@/store/chat-store';

export default function ChatConfigModal({ onClose }: { onClose: () => void }) {
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  const [provider, setProvider] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const setConfigLoaded = useChatStore((s) => s.setConfigLoaded);

  useEffect(() => {
    getModelPresets().then(setPresets).catch(() => {});
    getLlmConfig().then((c) => {
      if (c) { setBaseUrl(c.baseUrl); setModel(c.model); setApiKey(c.apiKey); }
    }).catch(() => {});
  }, []);

  function onProviderChange(p: string) {
    setProvider(p);
    const preset = presets.find((x) => x.provider === p);
    if (preset) { setBaseUrl(preset.baseUrl); setModel(preset.models[0] ?? ''); }
  }

  async function onSave() {
    if (!apiKey.trim() || !baseUrl.trim() || !model.trim()) return setError('请填写完整配置');
    setSaving(true); setError('');
    try {
      await saveLlmConfig({ apiKey: apiKey.trim(), baseUrl: baseUrl.trim(), model: model.trim() });
      setConfigLoaded(true, true);
      onClose();
    } catch (err) { setError(err instanceof Error ? err.message : '保存失败'); }
    finally { setSaving(false); }
  }

  const currentPreset = presets.find((x) => x.baseUrl === baseUrl);
  const modelOptions = currentPreset?.models ?? [];

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[1000]">
      <div className="bg-white rounded-xl p-6 w-[440px] max-h-[80vh] overflow-auto">
        <h3 className="mt-0">LLM 配置</h3>
        <label className="block mb-3">
          <span className="text-[13px] text-gray-600">供应商</span>
          <select value={provider} onChange={(e) => onProviderChange(e.target.value)} className="block w-full mt-1 px-2 py-1.5">
            <option value="">自定义</option>
            {presets.map((p) => <option key={p.provider} value={p.provider}>{p.provider}</option>)}
          </select>
        </label>
        <label className="block mb-3">
          <span className="text-[13px] text-gray-600">Base URL</span>
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" className="block w-full mt-1 px-2 py-1.5 box-border" />
        </label>
        <label className="block mb-3">
          <span className="text-[13px] text-gray-600">模型</span>
          {modelOptions.length ? (
            <select value={model} onChange={(e) => setModel(e.target.value)} className="block w-full mt-1 px-2 py-1.5">
              {modelOptions.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o" className="block w-full mt-1 px-2 py-1.5 box-border" />
          )}
        </label>
        <label className="block mb-4">
          <span className="text-[13px] text-gray-600">API Key</span>
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." className="block w-full mt-1 px-2 py-1.5 box-border" />
        </label>
        {error ? <p className="text-red-700 text-[13px]">{error}</p> : null}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="px-4 py-1.5 cursor-pointer">取消</button>
          <button type="button" onClick={onSave} disabled={saving} className="px-4 py-1.5 cursor-pointer bg-blue-600 text-white border-none rounded">
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
}
