import { ArrowLeft, ArrowRight, CheckCircle2, Copy, ExternalLink } from "lucide-react";
import { useCallback, useState } from "react";

interface WizardStep {
  title: string;
  description: string;
  fields: WizardField[];
}

interface WizardField {
  key: string;
  label: string;
  type: "text" | "password" | "select";
  placeholder?: string;
  required?: boolean;
  options?: string[];
  helpText?: string;
  helpUrl?: string;
}

interface ConnectorWizardProps {
  connectorType: string;
  connectorName: string;
  onClose: () => void;
  onSave: (config: Record<string, string>) => void;
}

const WIZARD_CONFIGS: Record<string, WizardStep[]> = {
  "financial:tongdaxin": [
    {
      title: "通达信行情服务",
      description: "配置通达信行情数据连接。只读取行情时，不需要本地桌面客户端。",
      fields: [
        {
          key: "TDX_SERVER_IP",
          label: "服务 IP",
          type: "text",
          placeholder: "119.147.212.81",
          helpText: "通达信行情服务地址。默认使用公共行情服务器。"
        },
        {
          key: "TDX_SERVER_PORT",
          label: "服务端口",
          type: "text",
          placeholder: "7709",
          helpText: "默认端口为 7709。"
        }
      ]
    },
    {
      title: "交易桥接（可选）",
      description: "只有需要下单时才配置实盘易交易桥接。只看行情的连接器可以跳过这一步。",
      fields: [
        { key: "TDX_TRADE_SERVER", label: "交易服务 URL", type: "text", placeholder: "http://127.0.0.1:8888" },
        { key: "TDX_TRADE_ACCOUNT", label: "交易账号", type: "text", placeholder: "" },
        { key: "TDX_TRADE_PASSWORD", label: "交易密码", type: "password", placeholder: "" }
      ]
    }
  ],
  "financial:tonghuashun": [
    {
      title: "同花顺桌面客户端",
      description: "需要 Windows 上的同花顺下单客户端。macOS 和 Linux 部署建议使用远程桥接。",
      fields: [
        {
          key: "THS_CLIENT_PATH",
          label: "下单客户端路径",
          type: "text",
          placeholder: "C:\\Program Files\\THS\\xiadan.exe",
          required: true,
          helpText: "同花顺独立下单程序路径。"
        },
        {
          key: "THS_BROKER",
          label: "券商代码",
          type: "select",
          options: ["ths", "ht", "gj", "yh", "gf"],
          helpText: "选择本地客户端使用的券商适配器。"
        }
      ]
    },
    {
      title: "账号凭据",
      description: "交易凭据应尽量存放在操作系统密钥存储中。",
      fields: [
        { key: "THS_TRADE_ACCOUNT", label: "交易账号", type: "text", required: true },
        { key: "THS_TRADE_PASSWORD", label: "交易密码", type: "password", required: true }
      ]
    }
  ],
  "financial:eastmoney": [
    {
      title: "东方财富数据",
      description: "东方财富公开行情无需鉴权即可使用，高级端点可能需要 token。",
      fields: [
        {
          key: "EM_API_TOKEN",
          label: "API token（可选）",
          type: "password",
          placeholder: "使用公开端点可留空",
          helpText: "部分高级数据端点需要 token。"
        }
      ]
    }
  ],
  "financial:qmt": [
    {
      title: "MiniQMT",
      description: "需要本地 MiniQMT 安装和 XtQuant SDK。",
      fields: [
        {
          key: "QMT_PATH",
          label: "MiniQMT 安装路径",
          type: "text",
          required: true,
          placeholder: "C:\\QMT\\bin.x64",
          helpText: "MiniQMT bin 目录路径。"
        },
        { key: "QMT_ACCOUNT", label: "交易账号", type: "text", required: true },
        {
          key: "QMT_ACCOUNT_TYPE",
          label: "账号类型",
          type: "select",
          options: ["STOCK", "CREDIT"],
          helpText: "普通账户使用 STOCK，信用账户使用 CREDIT。"
        }
      ]
    }
  ],
  "platform:weixin": [
    {
      title: "个人微信 iLink Bot",
      description: "通过腾讯 iLink Bot API 连接个人微信账号，不需要公网 IP。",
      fields: [
        { key: "WEIXIN_ILINK_APP_ID", label: "iLink App ID", type: "text", required: true, helpUrl: "https://ilink.qq.com" },
        { key: "WEIXIN_ILINK_APP_SECRET", label: "iLink App Secret", type: "password", required: true }
      ]
    }
  ],
  "platform:wecom": [
    {
      title: "WeCom",
      description: "使用企业微信 AI Bot WebSocket 连接进行双向消息收发。",
      fields: [
        { key: "WECOM_CORP_ID", label: "Corp ID", type: "text", required: true, helpUrl: "https://work.weixin.qq.com" },
        { key: "WECOM_AGENT_ID", label: "Agent ID", type: "text", required: true },
        { key: "WECOM_SECRET", label: "Agent secret", type: "password", required: true },
        {
          key: "WECOM_WS_ENABLED",
          label: "启用 WebSocket",
          type: "select",
          options: ["1", "0"],
          helpText: "设为 1 可启用双向消息。"
        }
      ]
    }
  ],
  "platform:telegram": [
    {
      title: "Telegram Bot",
      description: "使用 BotFather 创建 bot，然后在这里粘贴 bot token。",
      fields: [
        {
          key: "TELEGRAM_BOT_TOKEN",
          label: "Bot token",
          type: "password",
          required: true,
          helpUrl: "https://t.me/BotFather",
          helpText: "从 @BotFather 获取 token。"
        }
      ]
    }
  ],
  "platform:qqbot": [
    {
      title: "QQ Bot",
      description: "在 QQ 开放平台创建 bot 并配置凭据。",
      fields: [
        { key: "QQBOT_APP_ID", label: "App ID", type: "text", required: true, helpUrl: "https://q.qq.com" },
        { key: "QQBOT_TOKEN", label: "Token", type: "password", required: true },
        { key: "QQBOT_APP_SECRET", label: "App secret", type: "password" },
        { key: "QQBOT_WS_ENABLED", label: "启用 WebSocket", type: "select", options: ["1", "0"] }
      ]
    }
  ],
  "platform:discord": [
    {
      title: "Discord Bot",
      description: "在 Discord Developer Portal 创建 bot 并配置 token。",
      fields: [
        {
          key: "DISCORD_BOT_TOKEN",
          label: "Bot token",
          type: "password",
          required: true,
          helpUrl: "https://discord.com/developers/applications"
        }
      ]
    }
  ]
};

export function ConnectorWizard({ connectorType, connectorName, onClose, onSave }: ConnectorWizardProps) {
  const wizardKey = `${connectorType}:${connectorName}`;
  const steps = WIZARD_CONFIGS[wizardKey] || [];
  const [currentStep, setCurrentStep] = useState(0);
  const [values, setValues] = useState<Record<string, string>>({});

  const handleChange = useCallback((key: string, value: string) => {
    setValues((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleNext = useCallback(() => {
    if (currentStep < steps.length - 1) {
      setCurrentStep((step) => step + 1);
    } else {
      onSave(values);
    }
  }, [currentStep, onSave, steps.length, values]);

  const handleBack = useCallback(() => {
    if (currentStep > 0) setCurrentStep((step) => step - 1);
    else onClose();
  }, [currentStep, onClose]);

  if (!steps.length) {
    return (
      <div className="wizard-panel">
        <div className="notice info">
          <span>当前没有可用于 {wizardKey} 的配置向导。</span>
        </div>
        <button className="small-button" onClick={onClose} type="button">
          关闭
        </button>
      </div>
    );
  }

  const step = steps[currentStep];
  const isLast = currentStep === steps.length - 1;
  const requiredMissing = step.fields.filter((field) => field.required && !values[field.key]?.trim());

  const envSnippet = Object.entries(values)
    .filter(([, value]) => value.trim())
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");

  return (
    <div className="wizard-panel">
      <div className="wizard-header">
        <div className="wizard-progress">
          {steps.map((_, index) => (
            <span key={index} className={`wizard-dot ${index === currentStep ? "active" : index < currentStep ? "done" : ""}`} />
          ))}
        </div>
        <h3>{step.title}</h3>
        <p className="muted">{step.description}</p>
      </div>

      <div className="wizard-fields">
        {step.fields.map((field) => (
          <div key={field.key} className="wizard-field">
            <label>
              {field.label}
              {field.required && <span className="required">*</span>}
            </label>
            {field.type === "select" ? (
              <select value={values[field.key] || ""} onChange={(event) => handleChange(field.key, event.target.value)}>
                <option value="">请选择...</option>
                {field.options?.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type={field.type}
                value={values[field.key] || ""}
                onChange={(event) => handleChange(field.key, event.target.value)}
                placeholder={field.placeholder}
              />
            )}
            {field.helpText && <span className="help-text">{field.helpText}</span>}
            {field.helpUrl && (
              <a href={field.helpUrl} target="_blank" rel="noopener noreferrer" className="help-link">
                <ExternalLink size={12} /> 帮助
              </a>
            )}
          </div>
        ))}
      </div>

      {isLast && envSnippet && (
        <div className="wizard-env-preview">
          <div className="section-header">
            <h4>环境变量预览</h4>
            <button className="btn-icon" onClick={() => navigator.clipboard.writeText(envSnippet)} title="复制" type="button">
              <Copy size={14} />
            </button>
          </div>
          <pre className="env-block">{envSnippet}</pre>
          <p className="muted">请将这些值加入 Agent 启动环境，然后重启 Agent 进程。</p>
        </div>
      )}

      <div className="wizard-actions">
        <button className="small-button" onClick={handleBack} type="button">
          <ArrowLeft size={14} /> {currentStep === 0 ? "取消" : "上一步"}
        </button>
        <button className="primary-button" onClick={handleNext} disabled={requiredMissing.length > 0} type="button">
          {isLast ? (
            <>
              <CheckCircle2 size={14} /> 完成
            </>
          ) : (
            <>
              下一步 <ArrowRight size={14} />
            </>
          )}
        </button>
      </div>
    </div>
  );
}
