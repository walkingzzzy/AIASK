import { useState } from "react";
import { Code, Edit, X } from "lucide-react";
import { CodeEditor, CodeViewer } from "./CodeEditor";
import "./EditableCodeBlock.css";

interface EditableCodeBlockProps {
  code: string;
  language: string;
  filename?: string;
  onSave?: (content: string, filename: string) => Promise<void>;
}

export function EditableCodeBlock({
  code,
  language,
  filename,
  onSave,
}: EditableCodeBlockProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedCode, setEditedCode] = useState(code);
  const [saveFilename, setSaveFilename] = useState(filename || "");
  const [isSaving, setIsSaving] = useState(false);

  const handleEdit = () => {
    setIsEditing(true);
    setEditedCode(code);
  };

  const handleCancel = () => {
    setIsEditing(false);
    setEditedCode(code);
  };

  const handleSave = async () => {
    if (!saveFilename.trim()) {
      alert("请输入文件名");
      return;
    }

    setIsSaving(true);
    try {
      await onSave?.(editedCode, saveFilename);
      setIsEditing(false);
    } catch (error) {
      console.error("保存失败:", error);
      alert("保存失败，请重试");
    } finally {
      setIsSaving(false);
    }
  };

  if (!isEditing) {
    return (
      <div className="editable-code-block">
        <CodeViewer code={code} language={language} filename={filename} />
        {onSave && (
          <button
            onClick={handleEdit}
            className="edit-code-btn"
            title="编辑代码"
          >
            <Edit size={14} />
            <span>编辑</span>
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="editable-code-block editing">
      <div className="save-controls">
        <div className="save-filename-group">
          <label>保存为：</label>
          <input
            type="text"
            value={saveFilename}
            onChange={(e) => setSaveFilename(e.target.value)}
            placeholder="example.py"
            className="filename-input"
          />
        </div>
        <div className="save-actions">
          <button
            onClick={handleCancel}
            className="btn-cancel"
            disabled={isSaving}
          >
            <X size={16} />
            取消
          </button>
          <button
            onClick={handleSave}
            className="btn-save"
            disabled={isSaving || !saveFilename.trim()}
          >
            <Code size={16} />
            {isSaving ? "保存中..." : "保存文件"}
          </button>
        </div>
      </div>
      <CodeEditor
        language={language}
        value={editedCode}
        onChange={setEditedCode}
        height="400px"
        filename={saveFilename || filename}
      />
    </div>
  );
}
