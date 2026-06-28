import { EditableCodeBlock } from "./EditableCodeBlock";
import "./MessageContent.css";

interface MessageContentProps {
  content: string;
  role: "user" | "assistant" | "system";
  onSaveCode?: (content: string, filename: string) => Promise<void>;
}

// 简单的代码块解析器
function parseCodeBlocks(content: string) {
  const parts: Array<{ type: "text" | "code"; content: string; language?: string; filename?: string }> = [];

  // 匹配 ```language 或 ```language:filename 格式的代码块
  const codeBlockRegex = /```(\w+)(?::([^\n]+))?\n([\s\S]*?)```/g;

  let lastIndex = 0;
  let match;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    // 添加代码块之前的文本
    if (match.index > lastIndex) {
      parts.push({
        type: "text",
        content: content.slice(lastIndex, match.index),
      });
    }

    // 添加代码块
    parts.push({
      type: "code",
      language: match[1] || "text",
      filename: match[2] || undefined,
      content: match[3].trim(),
    });

    lastIndex = match.index + match[0].length;
  }

  // 添加剩余的文本
  if (lastIndex < content.length) {
    parts.push({
      type: "text",
      content: content.slice(lastIndex),
    });
  }

  return parts;
}

export function MessageContent({ content, role, onSaveCode }: MessageContentProps) {
  const parts = parseCodeBlocks(content);

  // 如果没有代码块，直接显示文本
  if (parts.length === 1 && parts[0].type === "text") {
    return <div className="message-text">{content}</div>;
  }

  // 渲染混合内容
  return (
    <div className="message-content-parts">
      {parts.map((part, index) => {
        if (part.type === "text") {
          return (
            <div key={index} className="message-text">
              {part.content.split("\n").map((line, i) => (
                <p key={i}>{line || " "}</p>
              ))}
            </div>
          );
        } else {
          return (
            <EditableCodeBlock
              key={index}
              code={part.content}
              language={part.language || "text"}
              filename={part.filename}
              onSave={role === "assistant" ? onSaveCode : undefined}
            />
          );
        }
      })}
    </div>
  );
}
