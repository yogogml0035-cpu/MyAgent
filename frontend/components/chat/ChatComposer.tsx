"use client";

import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import type { ModelDisplayOption } from "../../app/model-ui";
import type { SkillOption } from "../../app/task-state";
import { FILE_INPUT_ACCEPT, SUPPORTED_UPLOAD_LABEL } from "../../app/file-upload";
import { shouldSubmitComposerKey } from "../../app/workspace-view";

const FILE_INPUT_ID = "document-files";

type ChatComposerProps = {
  activeTask: boolean;
  canSend: boolean;
  input: string;
  isBusy: boolean;
  model: string;
  modelDisplayOptions: ModelDisplayOption[];
  selectedFiles: File[];
  selectedModelDisplay: ModelDisplayOption;
  selectedModelRunnable: boolean;
  selectedSkills: SkillOption[];
  skillOptions: SkillOption[];
  uploadCount: number;
  onFileSelection: (files: File[]) => void;
  onRemoveFile: (index: number) => void;
  onRemoveSkill: (skillName: string) => void;
  onInputChange: (value: string) => void;
  onModelChange: (model: string) => void;
  onSelectSkill: (skill: SkillOption) => void;
  onStop: () => Promise<void>;
  onSubmit: () => Promise<void>;
};

export function ChatComposer({
  activeTask,
  canSend,
  input,
  isBusy,
  model,
  modelDisplayOptions,
  selectedFiles,
  selectedModelDisplay,
  selectedModelRunnable,
  uploadCount,
  onFileSelection,
  onRemoveFile,
  onInputChange,
  onModelChange,
  onStop,
  onSubmit,
}: ChatComposerProps) {
  const [isModelPickerOpen, setIsModelPickerOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const modelPickerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (selectedFiles.length === 0 && fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [selectedFiles.length]);

  useEffect(() => {
    if (!isModelPickerOpen) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && modelPickerRef.current?.contains(target)) {
        return;
      }
      setIsModelPickerOpen(false);
    }

    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        setIsModelPickerOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isModelPickerOpen]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void onSubmit();
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    onFileSelection(Array.from(event.target.files ?? []));
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      shouldSubmitComposerKey({
        key: event.key,
        shiftKey: event.shiftKey,
        nativeIsComposing: event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229,
      })
    ) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form className="composerShell" onSubmit={handleSubmit}>
      <input
        accept={FILE_INPUT_ACCEPT}
        className="fileInput"
        id={FILE_INPUT_ID}
        multiple
        onChange={handleFileChange}
        ref={fileInputRef}
        type="file"
      />

      <div className="composerPanel">
        {selectedFiles.length > 0 ? (
          <div className="filePreviewShelf" data-testid="selected-file-card">
            <div className="filePreviewList" aria-label="已选文件">
              {selectedFiles.map((file, index) => (
                <div
                  className="fileChip"
                  data-testid="selected-file-item"
                  key={`${file.name}-${file.size}-${index}`}
                >
                  <strong title={file.name}>{file.name}</strong>
                  <button
                    aria-label={`移除 ${file.name}`}
                    className="removeFileButton"
                    onClick={() => onRemoveFile(index)}
                    title={`移除 ${file.name}`}
                    type="button"
                  >
                    <span className="removeFileGlyph" aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
            <label
              aria-label="更换已选文件"
              className="replaceFileButton"
              htmlFor={FILE_INPUT_ID}
              title="更换已选文件"
            >
              <svg aria-hidden="true" className="replaceFileIcon" fill="none" viewBox="0 0 24 24">
                <path
                  d="M6.4 9.2A6.7 6.7 0 0 1 18 6.8l1.4 1.4M17.6 14.8A6.7 6.7 0 0 1 6 17.2l-1.4-1.4M18.7 3.8v4.7h-4.7M5.3 20.2v-4.7h4.7"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.8"
                />
              </svg>
              <span>更换</span>
            </label>
          </div>
        ) : null}

        <textarea
          className="promptTextarea"
          onChange={(event) => onInputChange(event.target.value)}
          onKeyDown={handleComposerKeyDown}
          placeholder={activeTask ? "回复生成中，请稍候..." : "尽管问..."}
          rows={2}
          value={input}
        />

        <div className="composerControls">
          <label
            aria-label={`上传 ${SUPPORTED_UPLOAD_LABEL}`}
            className="roundButton addFileButton"
            htmlFor={FILE_INPUT_ID}
          >
            <span aria-hidden="true" />
          </label>

          {uploadCount > 0 ? <span className="uploadMeta">已上传 {uploadCount} 个文件</span> : null}

          <div className="composerSpacer" />

          <div className="modelPicker" ref={modelPickerRef}>
            <button
              aria-expanded={isModelPickerOpen}
              aria-haspopup="listbox"
              className="modelPickerTrigger"
              onClick={() => setIsModelPickerOpen((current) => !current)}
              type="button"
            >
              <span className="modelPickerLabel">{selectedModelDisplay.label}</span>
              <span className="modelChevron" aria-hidden="true" />
            </button>

            {isModelPickerOpen ? (
              <div aria-label="模型" className="modelPickerMenu" role="listbox">
                {modelDisplayOptions.map((option) => {
                  const isSelected = option.id === model;
                  const isDisabled = option.available === false;
                  return (
                    <button
                      aria-disabled={isDisabled}
                      aria-selected={isSelected}
                      className={[
                        "modelOption",
                        isSelected ? "modelOption-active" : "",
                        isDisabled ? "modelOption-disabled" : "",
                      ].filter(Boolean).join(" ")}
                      disabled={isDisabled}
                      key={option.id}
                      onClick={() => {
                        if (isDisabled) {
                          return;
                        }
                        onModelChange(option.id);
                        setIsModelPickerOpen(false);
                      }}
                      role="option"
                      type="button"
                    >
                      <span className="modelOptionCopy">
                        <span className="modelOptionTitle">
                          <span>{option.label}</span>
                          {option.badge ? <span className="modelBadge">{option.badge}</span> : null}
                          {option.available === false ? <span className="modelBadge modelBadge-muted">未配置</span> : null}
                        </span>
                        <small>{option.disabledReason ?? option.description}</small>
                      </span>
                      <span className="modelCheck" aria-hidden="true" />
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>

          {activeTask ? (
            <button
              aria-label="停止任务"
              className="sendButton stopAction"
              disabled={isBusy}
              onClick={() => void onStop()}
              type="button"
            >
              <svg aria-hidden="true" className="sendButtonIcon" fill="none" viewBox="0 0 24 24">
                <rect fill="currentColor" height="12" rx="2.5" width="12" x="6" y="6" />
              </svg>
            </button>
          ) : (
            <button
              aria-label={isBusy ? "发送中" : "发送"}
              className="sendButton"
              disabled={!canSend || isBusy || !selectedModelRunnable}
              type="submit"
            >
              <svg aria-hidden="true" className="sendButtonIcon" fill="none" viewBox="0 0 24 24">
                <path
                  d="M12 19V5m0 0-6 6m6-6 6 6"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2.4"
                />
              </svg>
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
