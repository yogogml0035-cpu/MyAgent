"use client";

import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  type SyntheticEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ModelDisplayOption } from "../../app/model-ui";
import {
  filterSkillOptions,
  findActiveSkillSlashToken,
  replaceActiveSkillSlashToken,
  type ActiveSkillSlashToken,
  type SkillOption,
} from "../../app/task-state";
import { FILE_INPUT_ACCEPT, SUPPORTED_UPLOAD_LABEL } from "../../app/file-upload";
import { shouldSubmitComposerKey } from "../../app/workspace-view";

const FILE_INPUT_ID = "document-files";

type ChatComposerProps = {
  activeTask: boolean;
  canSend: boolean;
  input: string;
  isComposerBusy: boolean;
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

function buildSkillSlashTokenKey(value: string, token: ActiveSkillSlashToken) {
  return `${token.start}:${token.end}:${value.slice(token.start, token.end)}`;
}

export function ChatComposer({
  activeTask,
  canSend,
  input,
  isComposerBusy,
  model,
  modelDisplayOptions,
  selectedFiles,
  selectedModelDisplay,
  selectedModelRunnable,
  selectedSkills,
  skillOptions,
  uploadCount,
  onFileSelection,
  onRemoveFile,
  onRemoveSkill,
  onInputChange,
  onModelChange,
  onSelectSkill,
  onStop,
  onSubmit,
}: ChatComposerProps) {
  const [isModelPickerOpen, setIsModelPickerOpen] = useState(false);
  const [isSkillPickerOpen, setIsSkillPickerOpen] = useState(false);
  const [activeSkillIndex, setActiveSkillIndex] = useState(0);
  const [activeSlashToken, setActiveSlashToken] = useState<ActiveSkillSlashToken | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const dismissedSkillSlashTokenRef = useRef<string | null>(null);
  const modelPickerRef = useRef<HTMLDivElement | null>(null);
  const skillPickerRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const skillPickerEnabled = !activeTask && !isComposerBusy && skillOptions.length > 0;
  const filteredSkillOptions = useMemo(
    () =>
      isSkillPickerOpen && activeSlashToken
        ? filterSkillOptions(skillOptions, activeSlashToken.query)
        : [],
    [activeSlashToken, isSkillPickerOpen, skillOptions],
  );
  const activeSkillOption = filteredSkillOptions[activeSkillIndex] ?? filteredSkillOptions[0];

  useEffect(() => {
    if (selectedFiles.length === 0 && fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [selectedFiles.length]);

  useEffect(() => {
    if (!skillPickerEnabled) {
      setIsSkillPickerOpen(false);
      setActiveSlashToken(null);
    }
  }, [skillPickerEnabled]);

  useEffect(() => {
    setActiveSkillIndex(0);
  }, [activeSlashToken?.query]);

  useEffect(() => {
    if (activeSkillIndex >= filteredSkillOptions.length) {
      setActiveSkillIndex(0);
    }
  }, [activeSkillIndex, filteredSkillOptions.length]);

  useEffect(() => {
    if (!isSkillPickerOpen) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (
        target instanceof Node &&
        (skillPickerRef.current?.contains(target) || textareaRef.current?.contains(target))
      ) {
        return;
      }
      const cursorIndex = textareaRef.current?.selectionStart ?? input.length;
      const token = activeSlashToken ?? findActiveSkillSlashToken(input, cursorIndex);
      if (token) {
        dismissedSkillSlashTokenRef.current = buildSkillSlashTokenKey(input, token);
      }
      setIsSkillPickerOpen(false);
      setActiveSlashToken(null);
    }

    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [activeSlashToken, input, isSkillPickerOpen]);

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

  function syncSkillPicker(value: string, cursorIndex: number) {
    if (!skillPickerEnabled) {
      setIsSkillPickerOpen(false);
      setActiveSlashToken(null);
      dismissedSkillSlashTokenRef.current = null;
      return;
    }

    const token = findActiveSkillSlashToken(value, cursorIndex);
    if (!token) {
      setActiveSlashToken(null);
      setIsSkillPickerOpen(false);
      dismissedSkillSlashTokenRef.current = null;
      return;
    }

    setActiveSlashToken(token);
    if (dismissedSkillSlashTokenRef.current === buildSkillSlashTokenKey(value, token)) {
      setIsSkillPickerOpen(false);
      return;
    }

    dismissedSkillSlashTokenRef.current = null;
    setIsSkillPickerOpen(true);
  }

  function focusTextareaAt(cursorIndex: number) {
    window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(cursorIndex, cursorIndex);
    });
  }

  function dismissSkillPicker() {
    const cursorIndex = textareaRef.current?.selectionStart ?? input.length;
    const token = activeSlashToken ?? findActiveSkillSlashToken(input, cursorIndex);
    if (token) {
      dismissedSkillSlashTokenRef.current = buildSkillSlashTokenKey(input, token);
    }
    setIsSkillPickerOpen(false);
    setActiveSlashToken(null);
  }

  function handleSkillSelect(skill: SkillOption) {
    const cursorIndex = textareaRef.current?.selectionStart ?? input.length;
    const token = activeSlashToken ?? findActiveSkillSlashToken(input, cursorIndex);
    const nextInput = replaceActiveSkillSlashToken(input, token);

    onSelectSkill(skill);
    onInputChange(nextInput.value);
    dismissedSkillSlashTokenRef.current = null;
    setIsSkillPickerOpen(false);
    setActiveSlashToken(null);
    setActiveSkillIndex(0);
    focusTextareaAt(nextInput.cursor);
  }

  function handleInputChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const nextValue = event.target.value;
    onInputChange(nextValue);
    syncSkillPicker(nextValue, event.target.selectionStart);
  }

  function handleTextareaSelectionChange(event: SyntheticEvent<HTMLTextAreaElement>) {
    syncSkillPicker(event.currentTarget.value, event.currentTarget.selectionStart);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (isSkillPickerOpen) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveSkillIndex((current) =>
          filteredSkillOptions.length === 0 ? 0 : (current + 1) % filteredSkillOptions.length,
        );
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveSkillIndex((current) =>
          filteredSkillOptions.length === 0
            ? 0
            : (current - 1 + filteredSkillOptions.length) % filteredSkillOptions.length,
        );
        return;
      }

      if (event.key === "Enter") {
        event.preventDefault();
        if (activeSkillOption) {
          handleSkillSelect(activeSkillOption);
        }
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        dismissSkillPicker();
        return;
      }
    }

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

        {selectedSkills.length > 0 ? (
          <div
            className="skillChipShelf"
            aria-label="已选 Skill"
            data-testid="selected-skill-shelf"
          >
            {selectedSkills.map((skill) => (
              <button
                aria-label={`移除 ${skill.name} skill`}
                className="skillChip"
                key={skill.name}
                onClick={() => onRemoveSkill(skill.name)}
                title={`移除 ${skill.name}`}
                type="button"
              >
                <span className="skillChipMarker" aria-hidden="true" />
                <span className="skillChipName">{skill.name}</span>
                <span className="skillChipRemove" aria-hidden="true" />
              </button>
            ))}
          </div>
        ) : null}

        <textarea
          aria-activedescendant={
            isSkillPickerOpen && activeSkillOption
              ? `skill-option-${activeSkillOption.name}`
              : undefined
          }
          aria-controls={isSkillPickerOpen ? "skill-picker-options" : undefined}
          aria-haspopup="listbox"
          className="promptTextarea"
          onChange={handleInputChange}
          onClick={handleTextareaSelectionChange}
          onKeyDown={handleComposerKeyDown}
          onSelect={handleTextareaSelectionChange}
          placeholder={activeTask ? "回复生成中，请稍候..." : "尽管问..."}
          ref={textareaRef}
          rows={2}
          value={input}
        />

        {isSkillPickerOpen ? (
          <div
            aria-label="Skill 选择器"
            className="skillPickerMenu"
            id="skill-picker-options"
            ref={skillPickerRef}
            role="listbox"
          >
            {filteredSkillOptions.length > 0 ? (
              filteredSkillOptions.map((skill, index) => (
                <button
                  aria-selected={index === activeSkillIndex}
                  className={[
                    "skillOption",
                    index === activeSkillIndex ? "skillOption-active" : "",
                  ].filter(Boolean).join(" ")}
                  id={`skill-option-${skill.name}`}
                  key={skill.name}
                  onClick={() => handleSkillSelect(skill)}
                  role="option"
                  type="button"
                >
                  <span className="skillOptionMarker" aria-hidden="true" />
                  <span className="skillOptionCopy">
                    <span className="skillOptionTitle">{skill.name}</span>
                    <small>{skill.description || "项目 Skill"}</small>
                  </span>
                </button>
              ))
            ) : (
              <div className="skillPickerEmpty" role="status">
                没有匹配的 skill
              </div>
            )}
          </div>
        ) : null}

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
              disabled={isComposerBusy}
              onClick={() => void onStop()}
              type="button"
            >
              <svg aria-hidden="true" className="sendButtonIcon" fill="none" viewBox="0 0 24 24">
                <rect fill="currentColor" height="12" rx="2.5" width="12" x="6" y="6" />
              </svg>
            </button>
          ) : (
            <button
              aria-label={isComposerBusy ? "发送中" : "发送"}
              className="sendButton"
              disabled={!canSend || isComposerBusy || !selectedModelRunnable}
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
