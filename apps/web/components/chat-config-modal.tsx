'use client';

import { type KeyboardEvent as ReactKeyboardEvent, useCallback, useEffect, useId, useRef, useState } from 'react';
import { getLlmConfig, saveLlmConfig, probeModels } from '@/lib/chat-api';
import { useChatStore } from '@/store/chat-store';

export default function ChatConfigModal({ onClose }: { onClose: () => void }) {
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const [detectedModels, setDetectedModels] = useState<string[]>([]);
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState('');
  const probeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setConfigLoaded = useChatStore((s) => s.setConfigLoaded);
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
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

  const doProbe = useCallback((url: string, key: string) => {
    if (!url.trim() || !key.trim()) {
      setDetectedModels([]);
      setProbeError('');
      return;
    }
    setProbing(true);
    setProbeError('');
    probeModels(url, key)
      .then((result) => {
        if (result.success && result.models.length > 0) {
          setDetectedModels(result.models);
          setProbeError('');
        } else {
          setDetectedModels([]);
          setProbeError(result.error || '未检测到可用模型');
        }
      })
      .catch(() => {
        setDetectedModels([]);
        setProbeError('检测请求失败');
      })
      .finally(() => setProbing(false));
  }, []);

  function scheduleProbe(url: string, key: string) {
    if (probeTimerRef.current) clearTimeout(probeTimerRef.current);
    probeTimerRef.current = setTimeout(() => doProbe(url, key), 600);
  }

  function onBaseUrlChange(value: string) {
    setBaseUrl(value);
    setError('');
    scheduleProbe(value, apiKey);
  }

  function onApiKeyChange(value: string) {
    setApiKey(value);
    setError('');
    scheduleProbe(baseUrl, value);
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

  const hasModels = detectedModels.length > 0;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[1000]" onClick={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="glass-strong rounded-2xl p-4 sm:p-6 w-full max-w-[440px] mx-4 max-h-[85vh] overflow-auto"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={handleTrapFocus}
      >
        <h2 id={titleId} className="mt-0">LLM 配置</h2>
        <p id={descriptionId} className="text-[13px] text-text-secondary mt-1 mb-4">
          填写 Base URL 和 API Key 后会自动检测可用模型。按 `Esc` 可关闭窗口。
        </p>

        <label className="block mb-3">
          <span className="text-[13px] text-text-secondary">Base URL</span>
          <input
            value={baseUrl}
            onChange={(e) => onBaseUrlChange(e.target.value)}
            placeholder="https://api.openai.com/v1"
            className="block w-full mt-1 px-2 py-1.5 box-border"
          />
        </label>

        <label className="block mb-3">
          <span className="text-[13px] text-text-secondary">API Key</span>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => onApiKeyChange(e.target.value)}
            placeholder="sk-..."
            className="block w-full mt-1 px-2 py-1.5 box-border"
          />
        </label>

        <label className="block mb-4">
          <span className="text-[13px] text-text-secondary">模型</span>
          {probing ? (
            <div className="mt-1 px-2 py-2 text-xs text-text-muted">正在检测可用模型...</div>
          ) : hasModels ? (
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="block w-full mt-1 px-2 py-1.5"
            >
              <option value="">选择模型</option>
              {detectedModels.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <>
              <input
                value={model}
                onChange={(e) => { setModel(e.target.value); setError(''); }}
                placeholder="gpt-4o"
                className="block w-full mt-1 px-2 py-1.5 box-border"
              />
              {probeError ? (
                <div className="mt-1 text-xs text-text-muted">{probeError}，可手动输入模型名称</div>
              ) : baseUrl.trim() && apiKey.trim() ? (
                <button
                  type="button"
                  onClick={() => doProbe(baseUrl, apiKey)}
                  className="mt-1 text-xs text-primary cursor-pointer bg-transparent border-none p-0 hover:underline"
                >
                  点击重新检测
                </button>
              ) : null}
            </>
          )}
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
