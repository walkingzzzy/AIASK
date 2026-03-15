'use client';

import { type KeyboardEvent as ReactKeyboardEvent, useEffect, useId, useRef, useState } from 'react';
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
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    getModelPresets().then(setPresets).catch(() => {});
    getLlmConfig().then((c) => {
      if (c) { setBaseUrl(c.baseUrl); setModel(c.model); setApiKey(c.apiKey); }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const previousActive = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = dialogRef.current?.querySelector<HTMLElement>('input, select, button, textarea, [href], [tabindex]:not([tabindex="-1"])');
    focusable?.focus();

    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    }

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      previousActive?.focus();
    };
  }, [onClose]);

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

  function handleTrapFocus(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Tab' || !dialogRef.current) return;

    const focusable = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>('input, select, button, textarea, [href], [tabindex]:not([tabindex="-1"])'),
    ).filter((element) => !element.hasAttribute('disabled'));

    if (focusable.length < 2) return;

    const currentIndex = focusable.indexOf(document.activeElement as HTMLElement);
    if (event.shiftKey) {
      if (currentIndex <= 0) {
        event.preventDefault();
        focusable[focusable.length - 1]?.focus();
      }
      return;
    }

    if (currentIndex === focusable.length - 1) {
      event.preventDefault();
      focusable[0]?.focus();
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[1000]" onClick={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="glass-strong rounded-2xl p-6 w-[440px] max-w-[92vw] max-h-[80vh] overflow-auto"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={handleTrapFocus}
      >
        <h2 id={titleId} className="mt-0">LLM 配置</h2>
        <p id={descriptionId} className="text-[13px] text-text-secondary mt-1 mb-4">配置对话模型供应商、基础地址、模型和 API Key。按 `Esc` 可关闭窗口。</p>
        <label className="block mb-3">
          <span className="text-[13px] text-text-secondary">供应商</span>
          <select value={provider} onChange={(e) => onProviderChange(e.target.value)} className="block w-full mt-1 px-2 py-1.5">
            <option value="">自定义</option>
            {presets.map((p) => <option key={p.provider} value={p.provider}>{p.provider}</option>)}
          </select>
        </label>
        <label className="block mb-3">
          <span className="text-[13px] text-text-secondary">Base URL</span>
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" className="block w-full mt-1 px-2 py-1.5 box-border" />
        </label>
        <label className="block mb-3">
          <span className="text-[13px] text-text-secondary">模型</span>
          {modelOptions.length ? (
            <select value={model} onChange={(e) => setModel(e.target.value)} className="block w-full mt-1 px-2 py-1.5">
              {modelOptions.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o" className="block w-full mt-1 px-2 py-1.5 box-border" />
          )}
        </label>
        <label className="block mb-4">
          <span className="text-[13px] text-text-secondary">API Key</span>
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." className="block w-full mt-1 px-2 py-1.5 box-border" />
        </label>
        {error ? <p className="text-danger text-[13px]" role="alert">{error}</p> : null}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="px-4 py-1.5 cursor-pointer">取消</button>
          <button type="button" onClick={onSave} disabled={saving} className="px-4 py-1.5 cursor-pointer bg-primary text-white border-none rounded">
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
}
