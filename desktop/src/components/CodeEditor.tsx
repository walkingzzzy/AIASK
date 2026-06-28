import { Editor, OnMount } from "@monaco-editor/react";
import { useState } from "react";
import { Copy, Check, Save } from "lucide-react";
import "./CodeEditor.css";

interface CodeEditorProps {
  language: string;
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  height?: string;
  onSave?: (content: string) => void;
  filename?: string;
}

export function CodeEditor({
  language,
  value,
  onChange,
  readOnly = false,
  height = "400px",
  onSave,
  filename,
}: CodeEditorProps) {
  const [editorValue, setEditorValue] = useState(value);
  const [copied, setCopied] = useState(false);

  const handleEditorChange = (value: string | undefined) => {
    const newValue = value || "";
    setEditorValue(newValue);
    onChange?.(newValue);
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(editorValue);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSave = () => {
    onSave?.(editorValue);
  };

  return (
    <div className="code-editor-wrapper">
      <div className="code-editor-header">
        <div className="code-editor-info">
          {filename && <span className="code-editor-filename">{filename}</span>}
          <span className="code-editor-language">{language}</span>
        </div>
        <div className="code-editor-actions">
          <button
            onClick={handleCopy}
            className="code-editor-action-btn"
            title="复制代码"
          >
            {copied ? <Check size={16} /> : <Copy size={16} />}
          </button>
          {onSave && !readOnly && (
            <button
              onClick={handleSave}
              className="code-editor-action-btn"
              title="保存到文件"
            >
              <Save size={16} />
            </button>
          )}
        </div>
      </div>
      <Editor
        height={height}
        language={language}
        value={editorValue}
        onChange={handleEditorChange}
        theme="vs-dark"
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 14,
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 2,
          wordWrap: "on",
        }}
      />
    </div>
  );
}

// 简化版代码查看器（只读，带复制按钮）
export function CodeViewer({
  language,
  code,
  filename,
}: {
  language: string;
  code: string;
  filename?: string;
}) {
  return (
    <CodeEditor
      language={language}
      value={code}
      readOnly={true}
      height="300px"
      filename={filename}
    />
  );
}
