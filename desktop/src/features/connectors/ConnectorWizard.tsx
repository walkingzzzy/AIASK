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
      title: "Tongdaxin quote server",
      description: "Configure the Tongdaxin market data connection. A local desktop client is not required for quote-only usage.",
      fields: [
        {
          key: "TDX_SERVER_IP",
          label: "Server IP",
          type: "text",
          placeholder: "119.147.212.81",
          helpText: "Tongdaxin quote server address. Public servers are used by default."
        },
        {
          key: "TDX_SERVER_PORT",
          label: "Server port",
          type: "text",
          placeholder: "7709",
          helpText: "Default port is 7709."
        }
      ]
    },
    {
      title: "Trading bridge (optional)",
      description: "Configure the ShiPanE trading bridge only when order placement is needed. Quote-only connectors can skip this step.",
      fields: [
        { key: "TDX_TRADE_SERVER", label: "Trading server URL", type: "text", placeholder: "http://127.0.0.1:8888" },
        { key: "TDX_TRADE_ACCOUNT", label: "Trading account", type: "text", placeholder: "" },
        { key: "TDX_TRADE_PASSWORD", label: "Trading password", type: "password", placeholder: "" }
      ]
    }
  ],
  "financial:tonghuashun": [
    {
      title: "Tonghuashun desktop client",
      description: "Requires the Tonghuashun order client on Windows. macOS and Linux deployments should use a remote bridge.",
      fields: [
        {
          key: "THS_CLIENT_PATH",
          label: "Order client path",
          type: "text",
          placeholder: "C:\\Program Files\\THS\\xiadan.exe",
          required: true,
          helpText: "Path to the standalone Tonghuashun order executable."
        },
        {
          key: "THS_BROKER",
          label: "Broker code",
          type: "select",
          options: ["ths", "ht", "gj", "yh", "gf"],
          helpText: "Select the broker adapter used by the local client."
        }
      ]
    },
    {
      title: "Account credentials",
      description: "Trading credentials should be stored in the operating system secret store when possible.",
      fields: [
        { key: "THS_TRADE_ACCOUNT", label: "Trading account", type: "text", required: true },
        { key: "THS_TRADE_PASSWORD", label: "Trading password", type: "password", required: true }
      ]
    }
  ],
  "financial:eastmoney": [
    {
      title: "Eastmoney data",
      description: "Public Eastmoney market data can be used without authentication. Advanced endpoints may require a token.",
      fields: [
        {
          key: "EM_API_TOKEN",
          label: "API token (optional)",
          type: "password",
          placeholder: "Leave blank for public endpoints",
          helpText: "Some advanced data endpoints require a token."
        }
      ]
    }
  ],
  "financial:qmt": [
    {
      title: "MiniQMT",
      description: "Requires a local MiniQMT installation and the XtQuant SDK.",
      fields: [
        {
          key: "QMT_PATH",
          label: "MiniQMT install path",
          type: "text",
          required: true,
          placeholder: "C:\\QMT\\bin.x64",
          helpText: "Path to the MiniQMT bin directory."
        },
        { key: "QMT_ACCOUNT", label: "Trading account", type: "text", required: true },
        {
          key: "QMT_ACCOUNT_TYPE",
          label: "Account type",
          type: "select",
          options: ["STOCK", "CREDIT"],
          helpText: "Use STOCK for cash accounts or CREDIT for margin accounts."
        }
      ]
    }
  ],
  "platform:weixin": [
    {
      title: "Personal Weixin iLink Bot",
      description: "Connect a personal Weixin account through Tencent iLink Bot API. A public IP is not required.",
      fields: [
        { key: "WEIXIN_ILINK_APP_ID", label: "iLink App ID", type: "text", required: true, helpUrl: "https://ilink.qq.com" },
        { key: "WEIXIN_ILINK_APP_SECRET", label: "iLink App Secret", type: "password", required: true }
      ]
    }
  ],
  "platform:wecom": [
    {
      title: "WeCom",
      description: "Use a WeCom AI Bot WebSocket connection for two-way messaging.",
      fields: [
        { key: "WECOM_CORP_ID", label: "Corp ID", type: "text", required: true, helpUrl: "https://work.weixin.qq.com" },
        { key: "WECOM_AGENT_ID", label: "Agent ID", type: "text", required: true },
        { key: "WECOM_SECRET", label: "Agent secret", type: "password", required: true },
        {
          key: "WECOM_WS_ENABLED",
          label: "Enable WebSocket",
          type: "select",
          options: ["1", "0"],
          helpText: "Set to 1 to enable two-way messaging."
        }
      ]
    }
  ],
  "platform:telegram": [
    {
      title: "Telegram Bot",
      description: "Create a bot with BotFather, then paste the bot token here.",
      fields: [
        {
          key: "TELEGRAM_BOT_TOKEN",
          label: "Bot token",
          type: "password",
          required: true,
          helpUrl: "https://t.me/BotFather",
          helpText: "Obtain the token from @BotFather."
        }
      ]
    }
  ],
  "platform:qqbot": [
    {
      title: "QQ Bot",
      description: "Create a bot in the QQ Open Platform and configure its credentials.",
      fields: [
        { key: "QQBOT_APP_ID", label: "App ID", type: "text", required: true, helpUrl: "https://q.qq.com" },
        { key: "QQBOT_TOKEN", label: "Token", type: "password", required: true },
        { key: "QQBOT_APP_SECRET", label: "App secret", type: "password" },
        { key: "QQBOT_WS_ENABLED", label: "Enable WebSocket", type: "select", options: ["1", "0"] }
      ]
    }
  ],
  "platform:discord": [
    {
      title: "Discord Bot",
      description: "Create a bot in the Discord Developer Portal and configure its token.",
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
          <span>No configuration wizard is available for {wizardKey}.</span>
        </div>
        <button className="small-button" onClick={onClose} type="button">
          Close
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
                <option value="">Select...</option>
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
                <ExternalLink size={12} /> Help
              </a>
            )}
          </div>
        ))}
      </div>

      {isLast && envSnippet && (
        <div className="wizard-env-preview">
          <div className="section-header">
            <h4>Environment preview</h4>
            <button className="btn-icon" onClick={() => navigator.clipboard.writeText(envSnippet)} title="Copy" type="button">
              <Copy size={14} />
            </button>
          </div>
          <pre className="env-block">{envSnippet}</pre>
          <p className="muted">Add these values to the Agent environment, then restart the Agent process.</p>
        </div>
      )}

      <div className="wizard-actions">
        <button className="small-button" onClick={handleBack} type="button">
          <ArrowLeft size={14} /> {currentStep === 0 ? "Cancel" : "Back"}
        </button>
        <button className="primary-button" onClick={handleNext} disabled={requiredMissing.length > 0} type="button">
          {isLast ? (
            <>
              <CheckCircle2 size={14} /> Finish
            </>
          ) : (
            <>
              Next <ArrowRight size={14} />
            </>
          )}
        </button>
      </div>
    </div>
  );
}
