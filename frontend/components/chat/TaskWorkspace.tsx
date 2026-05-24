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
        isHistoryBusy={workspace.isHistoryBusy}
        onClearConversations={workspace.handleClearConversations}
        onDeleteConversation={workspace.handleDeleteConversation}
        onNewConversation={workspace.handleNewConversation}
        onRenameConversation={workspace.handleRenameConversation}
        onSelectConversation={workspace.handleSelectConversation}
      />

      <section className={workspace.hasConversation ? "chatWorkspace hasConversation" : "chatWorkspace isEmpty"}>
        <TaskConversation
          activeTask={workspace.activeTask}
          conversationStreamItems={workspace.conversationStreamItems}
          copiedCopyKey={workspace.copiedCopyKey}
          hasConversation={workspace.hasConversation}
          noticeMessages={workspace.noticeMessages}
          onCopyText={workspace.handleCopyText}
          onDownloadLogs={workspace.handleDownloadLogs}
          onDownloadArtifact={workspace.handleDownloadArtifact}
          onOpenArtifact={workspace.handleOpenArtifact}
        />

        <ChatComposer
          canSend={workspace.canSend}
          currentTaskActive={workspace.currentTaskActive}
          input={workspace.input}
          isComposerBusy={workspace.isComposerBusy}
          model={workspace.model}
          modelDisplayOptions={workspace.modelDisplayOptions}
          onFileSelection={workspace.handleFileSelection}
          onRemoveFile={workspace.handleRemoveFile}
          onRemoveSkill={workspace.handleRemoveSkill}
          onInputChange={workspace.setInput}
          onModelChange={workspace.setModel}
          onSelectSkill={workspace.handleSelectSkill}
          onStop={workspace.handleStop}
          onSubmit={workspace.handleSubmit}
          selectedFiles={workspace.selectedFiles}
          selectedModelDisplay={workspace.selectedModelDisplay}
          selectedModelRunnable={workspace.selectedModelRunnable}
          selectedSkills={workspace.selectedSkills}
          skillOptions={workspace.skillOptions}
          uploadCount={workspace.uploadCount}
        />
      </section>
    </main>
  );
}
