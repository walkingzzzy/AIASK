/**
 * FileUpload & FileDownload - 文件上传下载组件
 */

import { Download, Upload, X, FileText, AlertCircle, CheckCircle2 } from "lucide-react";
import { useRef, useState } from "react";
import { Button, StatusBadge } from "./ui";

export interface FileUploadProps {
  accept?: string;
  maxSize?: number; // bytes
  multiple?: boolean;
  onUpload: (files: File[]) => Promise<void>;
  disabled?: boolean;
}

/**
 * 文件上传组件
 *
 * @example
 * <FileUpload
 *   accept=".csv,.xlsx"
 *   maxSize={10 * 1024 * 1024}
 *   multiple
 *   onUpload={async (files) => {
 *     await api.uploadDataFiles(files);
 *   }}
 * />
 */
export function FileUpload({ accept, maxSize = 10 * 1024 * 1024, multiple = false, onUpload, disabled }: FileUploadProps) {
  const [uploading, setUploading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    setError(null);
    setSuccess(false);

    // 验证文件大小
    const oversized = files.filter((f) => f.size > maxSize);
    if (oversized.length > 0) {
      setError(`文件过大：${oversized.map((f) => f.name).join(", ")} (最大 ${(maxSize / 1024 / 1024).toFixed(1)}MB)`);
      return;
    }

    setSelectedFiles(files);
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;

    setUploading(true);
    setError(null);

    try {
      await onUpload(selectedFiles);
      setSuccess(true);
      setSelectedFiles([]);
      if (inputRef.current) {
        inputRef.current.value = "";
      }

      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  const handleRemoveFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="file-upload">
      <div className="file-upload-input">
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          onChange={handleFileSelect}
          disabled={disabled || uploading}
          id="file-upload-input"
        />
        <label htmlFor="file-upload-input" className={disabled ? "disabled" : ""}>
          <Upload size={20} />
          {multiple ? "选择文件" : "选择单个文件"}
          {accept && <span className="file-upload-hint">({accept})</span>}
        </label>
      </div>

      {selectedFiles.length > 0 && (
        <div className="file-upload-list">
          {selectedFiles.map((file, i) => (
            <div key={i} className="file-upload-item">
              <FileText size={16} />
              <span className="file-name">{file.name}</span>
              <span className="file-size">({(file.size / 1024).toFixed(1)} KB)</span>
              {!uploading && (
                <button type="button" onClick={() => handleRemoveFile(i)} className="file-remove">
                  <X size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="file-upload-error">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {success && (
        <div className="file-upload-success">
          <CheckCircle2 size={16} />
          上传成功
        </div>
      )}

      {selectedFiles.length > 0 && (
        <Button onClick={handleUpload} disabled={uploading || disabled} tone="info">
          {uploading ? "上传中..." : `上传 ${selectedFiles.length} 个文件`}
        </Button>
      )}
    </div>
  );
}

export interface FileDownloadProps {
  filename: string;
  url?: string;
  getData?: () => Promise<Blob>;
  disabled?: boolean;
  children?: React.ReactNode;
}

/**
 * 文件下载组件
 *
 * @example
 * <FileDownload
 *   filename="report.csv"
 *   getData={async () => {
 *     const data = await api.exportReport();
 *     return new Blob([data], { type: 'text/csv' });
 *   }}
 * >
 *   导出报告
 * </FileDownload>
 */
export function FileDownload({ filename, url, getData, disabled, children }: FileDownloadProps) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    setDownloading(true);
    setError(null);

    try {
      let blob: Blob;

      if (url) {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`下载失败: ${response.statusText}`);
        }
        blob = await response.blob();
      } else if (getData) {
        blob = await getData();
      } else {
        throw new Error("必须提供 url 或 getData");
      }

      // 创建下载链接
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(blobUrl);
    } catch (err) {
      console.error("Download error:", err);
      setError(err instanceof Error ? err.message : "下载失败");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="file-download">
      <Button onClick={handleDownload} disabled={downloading || disabled} icon={<Download size={16} />}>
        {downloading ? "下载中..." : children || `下载 ${filename}`}
      </Button>
      {error && (
        <div className="file-download-error">
          <AlertCircle size={16} />
          {error}
        </div>
      )}
    </div>
  );
}

/**
 * 批量文件下载
 */
export interface BatchDownloadProps {
  files: Array<{ filename: string; url: string }>;
  disabled?: boolean;
}

export function BatchDownload({ files, disabled }: BatchDownloadProps) {
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const handleBatchDownload = async () => {
    setDownloading(true);
    setProgress(0);
    setError(null);

    try {
      for (let i = 0; i < files.length; i++) {
        const { filename, url } = files[i];

        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`下载失败: ${filename}`);
        }

        const blob = await response.blob();
        const blobUrl = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(blobUrl);

        setProgress(Math.round(((i + 1) / files.length) * 100));

        // 延迟避免浏览器阻止多个下载
        if (i < files.length - 1) {
          await new Promise((resolve) => setTimeout(resolve, 500));
        }
      }
    } catch (err) {
      console.error("Batch download error:", err);
      setError(err instanceof Error ? err.message : "批量下载失败");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="batch-download">
      <Button onClick={handleBatchDownload} disabled={downloading || disabled || files.length === 0} icon={<Download size={16} />}>
        {downloading ? `下载中 (${progress}%)` : `批量下载 (${files.length} 个文件)`}
      </Button>
      {error && (
        <div className="batch-download-error">
          <AlertCircle size={16} />
          {error}
        </div>
      )}
    </div>
  );
}
