import { ChevronDown } from "lucide-react";
import { useState, useEffect } from "react";
import { Button } from "./ui";

interface ModelOption {
  id: string;
  provider: string;
  model: string;
  base_url?: string;
  name?: string;
}

interface ModelSelectorProps {
  current: { provider: string; model: string };
  available: ModelOption[];
  onChange: (model: ModelOption) => Promise<void>;
  disabled?: boolean;
}

const MODEL_PRESETS: ModelOption[] = [
  {
    id: "openai-gpt4",
    provider: "openai",
    model: "gpt-4-turbo-preview",
    base_url: "https://api.openai.com/v1",
    name: "OpenAI GPT-4 官方"
  },
  {
    id: "openai-gpt35",
    provider: "openai",
    model: "gpt-3.5-turbo",
    base_url: "https://api.openai.com/v1",
    name: "OpenAI GPT-3.5 官方"
  },
  {
    id: "claude-opus",
    provider: "anthropic",
    model: "claude-3-opus-20240229",
    base_url: "https://api.anthropic.com",
    name: "Claude 3 Opus 官方"
  },
  {
    id: "claude-sonnet",
    provider: "anthropic",
    model: "claude-3-sonnet-20240229",
    base_url: "https://api.anthropic.com",
    name: "Claude 3 Sonnet 官方"
  },
  {
    id: "deepseek",
    provider: "openai",
    model: "deepseek-chat",
    base_url: "https://api.deepseek.com/v1",
    name: "DeepSeek"
  },
  {
    id: "ollama-qwen",
    provider: "ollama",
    model: "qwen2.5:latest",
    base_url: "http://localhost:11434/v1",
    name: "Ollama Qwen (本地)"
  }
];

export function ModelSelector({ current, available, onChange, disabled }: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const currentDisplay = current.model || "未选择模型";
  const allOptions = [...MODEL_PRESETS, ...available];

  // 去重
  const uniqueOptions = allOptions.reduce((acc, option) => {
    const key = `${option.provider}-${option.model}`;
    if (!acc.find(item => `${item.provider}-${item.model}` === key)) {
      acc.push(option);
    }
    return acc;
  }, [] as ModelOption[]);

  async function handleSelect(option: ModelOption) {
    if (busy || disabled) return;

    setIsOpen(false);
    setBusy(true);
    try {
      await onChange(option);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as HTMLElement;
      if (!target.closest(".model-selector")) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("click", handleClickOutside);
      return () => document.removeEventListener("click", handleClickOutside);
    }
  }, [isOpen]);

  return (
    <div className="model-selector" style={{ position: "relative", display: "inline-block" }}>
      <Button
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled || busy}
        tone="neutral"
        style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
      >
        {busy ? "切换中..." : currentDisplay}
        <ChevronDown size={16} style={{ transform: isOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
      </Button>

      {isOpen && (
        <div
          className="model-dropdown"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            marginTop: "0.25rem",
            background: "white",
            border: "1px solid #e5e7eb",
            borderRadius: "0.375rem",
            boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
            zIndex: 50,
            minWidth: "280px",
            maxHeight: "400px",
            overflowY: "auto"
          }}
        >
          <div style={{ padding: "0.5rem 0" }}>
            {uniqueOptions.map((option) => {
              const isCurrent = option.provider === current.provider && option.model === current.model;
              return (
                <button
                  key={option.id}
                  onClick={() => handleSelect(option)}
                  style={{
                    width: "100%",
                    padding: "0.5rem 1rem",
                    textAlign: "left",
                    border: "none",
                    background: isCurrent ? "#f3f4f6" : "transparent",
                    cursor: "pointer",
                    transition: "background 0.15s"
                  }}
                  onMouseEnter={(e) => {
                    if (!isCurrent) e.currentTarget.style.background = "#f9fafb";
                  }}
                  onMouseLeave={(e) => {
                    if (!isCurrent) e.currentTarget.style.background = "transparent";
                  }}
                >
                  <div style={{ fontWeight: 500, fontSize: "0.875rem" }}>
                    {option.name || option.model}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: "0.125rem" }}>
                    {option.provider} • {option.model}
                  </div>
                  {option.base_url && (
                    <div style={{ fontSize: "0.7rem", color: "#9ca3af", marginTop: "0.125rem" }}>
                      {option.base_url}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
