"use client";

import { useTaskWorkspace } from "../../hooks/use-task-workspace";
import { ChatComposer } from "./ChatComposer";
import { ChatSidebar } from "./ChatSidebar";
import { TaskConversation } from "./TaskConversation";

export function TaskWorkspace() {
  const workspace = useTaskWorkspace();

  return (
    <main className="agentShell">
      <ChatSidebar
        historyItems={workspace.historyItems}
        onNewConversation={workspace.handleNewConversation}
        onSelectConversation={workspace.handleSelectConversation}
      />

      <section className={workspace.hasConversation ? "chatWorkspace hasConversation" : "chatWorkspace isEmpty"}>
        <TaskConversation
          conversationStreamItems={workspace.conversationStreamItems}
          copiedCopyKey={workspace.copiedCopyKey}
          expandedReasoningRuns={workspace.expandedReasoningRuns}
          hasConversation={workspace.hasConversation}
          noticeMessages={workspace.noticeMessages}
          onCopyLogs={workspace.handleCopyLogs}
          onCopyText={workspace.handleCopyText}
          onDownloadArtifact={workspace.handleDownloadArtifact}
          onOpenArtifact={workspace.handleOpenArtifact}
          onToggleReasoningRun={workspace.toggleReasoningRun}
        />

        <ChatComposer
          activeTask={workspace.activeTask}
          canSend={workspace.canSend}
          input={workspace.input}
          isBusy={workspace.isBusy}
          model={workspace.model}
          modelDisplayOptions={workspace.modelDisplayOptions}
          onClearFiles={workspace.handleClearFiles}
          onFileSelection={workspace.handleFileSelection}
          onInputChange={workspace.setInput}
          onModelChange={workspace.setModel}
          onStop={workspace.handleStop}
          onSubmit={workspace.handleSubmit}
          selectedFileNames={workspace.selectedFileNames}
          selectedFileSize={workspace.selectedFileSize}
          selectedFiles={workspace.selectedFiles}
          selectedModelDisplay={workspace.selectedModelDisplay}
          uploadCount={workspace.uploadCount}
        />
      </section>
    </main>
  );
}
