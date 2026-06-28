import { Upload, X, File, FileText, Image as ImageIcon } from "lucide-react";
import { useState, useRef } from "react";
import { Button } from "./ui";

interface FileUploadDialogProps {
  onUpload: (files: File[]) => Promise<void>;
  onClose: () => void;
  accept?: string;
  multiple?: boolean;
}

export function FileUploadDialog({ onUpload, onClose, accept, multiple = true }: FileUploadDialogProps) {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFileSelect(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    setSelectedFiles(files);
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const files = Array.from(event.dataTransfer.files);
    setSelectedFiles(files);
  }

  function handleDragOver(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
  }

  function removeFile(index: number) {
    setSelectedFiles(selectedFiles.filter((_, i) => i !== index));
  }

  async function handleSubmit() {
    if (!selectedFiles.length) return;

    setBusy(true);
    try {
      await onUpload(selectedFiles);
      onClose();
    } catch (error) {
      console.error("上传文件失败:", error);
      alert(`上传失败: ${error}`);
    } finally {
      setBusy(false);
    }
  }

  function getFileIcon(file: File) {
    if (file.type.startsWith("image/")) return <ImageIcon size={16} />;
    if (file.type.includes("text") || file.type.includes("json")) return <FileText size={16} />;
    return <File size={16} />;
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <div
      className="dialog-overlay"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="dialog-content"
        style={{
          background: "white",
          borderRadius: "0.5rem",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1)",
          width: "90%",
          maxWidth: "600px",
          maxHeight: "90vh",
          overflow: "auto"
        }}
      >
        <div
          className="dialog-header"
          style={{
            padding: "1rem 1.5rem",
            borderBottom: "1px solid #e5e7eb",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between"
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Upload size={20} />
            <h2 style={{ fontSize: "1.125rem", fontWeight: 600, margin: 0 }}>上传文件</h2>
          </div>
          <button
            onClick={onClose}
            style={{
              border: "none",
              background: "transparent",
              cursor: "pointer",
              padding: "0.25rem",
              display: "flex",
              alignItems: "center"
            }}
          >
            <X size={20} />
          </button>
        </div>

        <div className="dialog-body" style={{ padding: "1.5rem" }}>
          <input
            ref={fileInputRef}
            data-testid="file-upload-input"
            type="file"
            onChange={handleFileSelect}
            accept={accept}
            multiple={multiple}
            style={{ display: "none" }}
          />

          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: "2px dashed #d1d5db",
              borderRadius: "0.5rem",
              padding: "2rem",
              textAlign: "center",
              cursor: "pointer",
              background: "#f9fafb",
              transition: "all 0.2s"
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = "#3b82f6";
              e.currentTarget.style.background = "#eff6ff";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = "#d1d5db";
              e.currentTarget.style.background = "#f9fafb";
            }}
          >
            <Upload size={48} style={{ margin: "0 auto 1rem", color: "#9ca3af" }} />
            <p style={{ fontSize: "1rem", fontWeight: 500, marginBottom: "0.5rem" }}>
              点击或拖拽文件到此处
            </p>
            <p style={{ fontSize: "0.875rem", color: "#6b7280" }}>
              {multiple ? "支持多文件上传" : "仅支持单文件上传"}
            </p>
            {accept && (
              <p style={{ fontSize: "0.75rem", color: "#9ca3af", marginTop: "0.5rem" }}>
                支持的格式: {accept}
              </p>
            )}
          </div>

          {selectedFiles.length > 0 && (
            <div style={{ marginTop: "1.5rem" }}>
              <h3 style={{ fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.5rem" }}>
                已选择 {selectedFiles.length} 个文件
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {selectedFiles.map((file, index) => (
                  <div
                    key={index}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "0.75rem",
                      border: "1px solid #e5e7eb",
                      borderRadius: "0.375rem",
                      background: "white"
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flex: 1 }}>
                      {getFileIcon(file)}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontSize: "0.875rem", fontWeight: 500, margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {file.name}
                        </p>
                        <p style={{ fontSize: "0.75rem", color: "#6b7280", margin: 0 }}>
                          {formatFileSize(file.size)}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeFile(index);
                      }}
                      style={{
                        border: "none",
                        background: "transparent",
                        cursor: "pointer",
                        padding: "0.25rem",
                        display: "flex",
                        alignItems: "center",
                        color: "#ef4444"
                      }}
                    >
                      <X size={16} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div
          className="dialog-footer"
          style={{
            padding: "1rem 1.5rem",
            borderTop: "1px solid #e5e7eb",
            display: "flex",
            justifyContent: "flex-end",
            gap: "0.5rem"
          }}
        >
          <Button onClick={onClose} tone="neutral" disabled={busy}>
            取消
          </Button>
          <Button
            data-testid="file-upload-submit"
            onClick={() => void handleSubmit()}
            tone="success"
            disabled={!selectedFiles.length || busy}
            busy={busy}
          >
            上传 {selectedFiles.length > 0 && `(${selectedFiles.length})`}
          </Button>
        </div>
      </div>
    </div>
  );
}

interface FileUploadButtonProps {
  onUpload: (files: File[]) => Promise<void>;
  accept?: string;
  multiple?: boolean;
  disabled?: boolean;
}

export function FileUploadButton({ onUpload, accept, multiple = true, disabled }: FileUploadButtonProps) {
  const [showDialog, setShowDialog] = useState(false);

  return (
    <>
      <Button
        data-testid="file-upload-button"
        onClick={() => setShowDialog(true)}
        tone="success"
        icon={<Upload size={16} />}
        disabled={disabled}
      >
        上传文件
      </Button>
      {showDialog && (
        <FileUploadDialog
          onUpload={onUpload}
          onClose={() => setShowDialog(false)}
          accept={accept}
          multiple={multiple}
        />
      )}
    </>
  );
}
