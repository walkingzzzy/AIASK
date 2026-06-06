import { Settings, User, Database, Key, Globe } from "lucide-react";
import { ReactNode } from "react";

interface ConfigSection {
  id: string;
  title: string;
  icon: ReactNode;
  description: string;
  priority: "essential" | "recommended" | "optional";
}

interface ConfigSectionManagerProps {
  sections: ConfigSection[];
  activeSection?: string;
  onSectionChange: (sectionId: string) => void;
}

export function ConfigSectionManager({
  sections,
  activeSection,
  onSectionChange
}: ConfigSectionManagerProps) {
  const essentialSections = sections.filter(s => s.priority === "essential");
  const recommendedSections = sections.filter(s => s.priority === "recommended");
  const optionalSections = sections.filter(s => s.priority === "optional");

  return (
    <div className="config-section-manager">
      <div className="config-sidebar">
        {essentialSections.length > 0 && (
          <div className="section-group">
            <h4>必要配置</h4>
            {essentialSections.map(section => (
              <ConfigSectionButton
                key={section.id}
                section={section}
                isActive={activeSection === section.id}
                onClick={() => onSectionChange(section.id)}
              />
            ))}
          </div>
        )}

        {recommendedSections.length > 0 && (
          <div className="section-group">
            <h4>推荐配置</h4>
            {recommendedSections.map(section => (
              <ConfigSectionButton
                key={section.id}
                section={section}
                isActive={activeSection === section.id}
                onClick={() => onSectionChange(section.id)}
              />
            ))}
          </div>
        )}

        {optionalSections.length > 0 && (
          <div className="section-group">
            <h4>可选配置</h4>
            {optionalSections.map(section => (
              <ConfigSectionButton
                key={section.id}
                section={section}
                isActive={activeSection === section.id}
                onClick={() => onSectionChange(section.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ConfigSectionButton({
  section,
  isActive,
  onClick
}: {
  section: ConfigSection;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={`config-section-button ${isActive ? "active" : ""}`}
      onClick={onClick}
      type="button"
    >
      <div className="section-icon">{section.icon}</div>
      <div className="section-info">
        <strong>{section.title}</strong>
        <span>{section.description}</span>
      </div>
    </button>
  );
}

// 预定义的配置分区
export const DEFAULT_CONFIG_SECTIONS: ConfigSection[] = [
  {
    id: "connection",
    title: "连接配置",
    icon: <Globe size={16} />,
    description: "API 端点、Token 配置",
    priority: "essential"
  },
  {
    id: "user",
    title: "用户配置",
    icon: <User size={16} />,
    description: "用户信息、偏好设置",
    priority: "essential"
  },
  {
    id: "security",
    title: "安全配置",
    icon: <Key size={16} />,
    description: "权限、认证、密钥管理",
    priority: "recommended"
  },
  {
    id: "storage",
    title: "存储配置",
    icon: <Database size={16} />,
    description: "本地存储、缓存设置",
    priority: "optional"
  },
  {
    id: "advanced",
    title: "高级配置",
    icon: <Settings size={16} />,
    description: "调试、性能、实验功能",
    priority: "optional"
  }
];
