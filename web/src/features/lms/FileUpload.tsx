import { type ChangeEvent, useRef, useState } from "react";
import { type LmsFile, uploadFile } from "../../api-client/lms";
import { ApiError } from "../../api-client/http";
import { Icon } from "../../components/Icon";

interface FileUploadProps {
  classId: string;
  purpose: "content" | "prompt" | "submission";
  accept?: string;
  label?: string;
  hint?: string;
  onUploaded: (file: LmsFile) => void;
  disabled?: boolean;
  autoUpload?: boolean;
  onUploadingChange?: (uploading: boolean) => void;
}

function formatSize(bytes: number): string {
  if (bytes > 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function FileUpload({
  classId,
  purpose,
  accept,
  label = "Chọn tệp tải lên",
  hint,
  onUploaded,
  disabled = false,
  autoUpload = true,
  onUploadingChange,
}: FileUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<LmsFile | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(selected: File) {
    setFile(selected);
    setError(null);
    setUploadedFile(null);

    if (autoUpload) {
      await startUpload(selected);
    }
  }

  async function startUpload(fileToUpload = file) {
    if (!fileToUpload) return;
    setUploading(true);
    onUploadingChange?.(true);
    setProgress(0);
    setError(null);

    try {
      const result = await uploadFile(classId, fileToUpload, purpose, (pct) => {
        setProgress(pct);
      });
      setUploadedFile(result);
      onUploaded(result);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        // Specifically presents 413 (Payload Too Large) or 415 (Unsupported Media Type) or custom detail
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Không thể tải tệp lên. Vui lòng kiểm tra lại kết nối.");
      }
    } finally {
      setUploading(false);
      onUploadingChange?.(false);
    }
  }

  function onInputChange(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0];
    if (picked) {
      void handleFile(picked);
    }
  }

  function reset() {
    setFile(null);
    setError(null);
    setUploadedFile(null);
    setProgress(0);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className="lms-file-upload">
      <label className="field">
        <span>{label}</span>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          disabled={disabled || uploading}
          onChange={onInputChange}
        />
      </label>

      {hint && <p className="ea-muted lms-file-upload__hint">{hint}</p>}

      {file && (
        <div className="lms-file-upload__selected">
          <div className="lms-file-upload__file-info">
            <Icon name="file" />
            <span className="lms-file-upload__filename">{file.name}</span>
            <span className="ea-muted">({formatSize(file.size)})</span>
          </div>

          {!autoUpload && !uploading && !uploadedFile && (
            <button
              className="button button--primary button--sm"
              type="button"
              disabled={disabled || uploading}
              onClick={() => void startUpload()}
            >
              <Icon name="upload" /> Tải lên
            </button>
          )}

          {!uploading && (
            <button
              className="button button--ghost button--sm"
              type="button"
              onClick={reset}
              title="Chọn tệp khác"
            >
              Đổi tệp
            </button>
          )}
        </div>
      )}

      {uploading && (
        <div className="lms-file-upload__progress-wrap" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <div className="lms-file-upload__progress-bar">
            <div
              className="lms-file-upload__progress-fill"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="lms-file-upload__progress-text">Đang tải lên: {progress}%</span>
        </div>
      )}

      {uploadedFile && (
        <p className="lms-file-upload__success" role="status">
          <Icon name="check" /> Đã tải lên: <strong>{uploadedFile.filename}</strong>
        </p>
      )}

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
