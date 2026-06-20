import { useTranslation } from 'react-i18next';
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, ReactNode, RefObject, SetStateAction } from 'react';
import type { ChatMessage } from '../../types/types';
import type { Project, ProjectSession, LLMProvider } from '../../../../types/app';
import { getIntrinsicMessageKey } from '../../utils/messageKeys';
import { buildCleanView, type CleanDisplayItem } from '../../utils/cleanView';
import MessageComponent from './MessageComponent';
import WorkFold from './WorkFold';
import ProviderSelectionEmptyState from './ProviderSelectionEmptyState';

interface ChatMessagesPaneProps {
  scrollContainerRef: RefObject<HTMLDivElement>;
  onWheel: () => void;
  onTouchMove: () => void;
  isLoadingSessionMessages: boolean;
  chatMessages: ChatMessage[];
  selectedSession: ProjectSession | null;
  currentSessionId: string | null;
  provider: LLMProvider;
  setProvider: (provider: LLMProvider) => void;
  textareaRef: RefObject<HTMLTextAreaElement>;
  claudeModel: string;
  setClaudeModel: (model: string) => void;
  cursorModel: string;
  setCursorModel: (model: string) => void;
  codexModel: string;
  setCodexModel: (model: string) => void;
  geminiModel: string;
  setGeminiModel: (model: string) => void;
  tasksEnabled: boolean;
  isTaskMasterInstalled: boolean | null;
  onShowAllTasks?: (() => void) | null;
  setInput: Dispatch<SetStateAction<string>>;
  isLoadingMoreMessages: boolean;
  hasMoreMessages: boolean;
  totalMessages: number;
  sessionMessagesCount: number;
  visibleMessageCount: number;
  visibleMessages: ChatMessage[];
  loadEarlierMessages: () => void;
  loadAllMessages: () => void;
  allMessagesLoaded: boolean;
  isLoadingAllMessages: boolean;
  loadAllJustFinished: boolean;
  showLoadAllOverlay: boolean;
  createDiff: any;
  onFileOpen?: (filePath: string, diffInfo?: unknown) => void;
  onShowSettings?: () => void;
  onGrantToolPermission: (suggestion: { entry: string; toolName: string }) => { success: boolean };
  autoExpandTools?: boolean;
  showRawParameters?: boolean;
  showThinking?: boolean;
  selectedProject: Project;
  /** 精简视图默认值(总控对话默认 true): 折叠中间工作记录, 只显示每轮最后一段文本。 */
  cleanViewDefault?: boolean;
  /** 设了就把精简/详细偏好按这个 key 持久化到 localStorage(如 'controller'), 不设则不持久化。 */
  cleanViewKey?: string;
  /** 渲染在消息列表末尾(对话最后)的附加内容, 如"本对话新材料"卡片。 */
  messagesFooter?: ReactNode;
}

export default function ChatMessagesPane({
  scrollContainerRef,
  onWheel,
  onTouchMove,
  isLoadingSessionMessages,
  chatMessages,
  selectedSession,
  currentSessionId,
  provider,
  setProvider,
  textareaRef,
  claudeModel,
  setClaudeModel,
  cursorModel,
  setCursorModel,
  codexModel,
  setCodexModel,
  geminiModel,
  setGeminiModel,
  tasksEnabled,
  isTaskMasterInstalled,
  onShowAllTasks,
  setInput,
  isLoadingMoreMessages,
  hasMoreMessages,
  totalMessages,
  sessionMessagesCount,
  visibleMessageCount,
  visibleMessages,
  loadEarlierMessages,
  loadAllMessages,
  allMessagesLoaded,
  isLoadingAllMessages,
  loadAllJustFinished,
  showLoadAllOverlay,
  createDiff,
  onFileOpen,
  onShowSettings,
  onGrantToolPermission,
  autoExpandTools,
  showRawParameters,
  showThinking,
  selectedProject,
  cleanViewDefault,
  cleanViewKey,
  messagesFooter,
}: ChatMessagesPaneProps) {
  const { t } = useTranslation('chat');
  const messageKeyMapRef = useRef<WeakMap<ChatMessage, string>>(new WeakMap());
  const allocatedKeysRef = useRef<Set<string>>(new Set());
  const generatedMessageKeyCounterRef = useRef(0);

  // 精简视图: 折叠中间工作记录, 只看每轮最后一段文本。偏好可按 cleanViewKey 持久化。
  const [cleanView, setCleanView] = useState<boolean>(() => {
    if (cleanViewKey && typeof window !== 'undefined') {
      try {
        const v = window.localStorage.getItem('omni.chat.cleanView.' + cleanViewKey);
        if (v !== null) return v === '1';
      } catch { /* ignore */ }
    }
    return Boolean(cleanViewDefault);
  });
  useEffect(() => {
    if (!cleanViewKey || typeof window === 'undefined') return;
    try { window.localStorage.setItem('omni.chat.cleanView.' + cleanViewKey, cleanView ? '1' : '0'); } catch { /* ignore */ }
  }, [cleanView, cleanViewKey]);

  // Keep keys stable across prepends so existing MessageComponent instances retain local state.
  const getMessageKey = useCallback((message: ChatMessage) => {
    const existingKey = messageKeyMapRef.current.get(message);
    if (existingKey) {
      return existingKey;
    }

    const intrinsicKey = getIntrinsicMessageKey(message);
    let candidateKey = intrinsicKey;

    if (!candidateKey || allocatedKeysRef.current.has(candidateKey)) {
      do {
        generatedMessageKeyCounterRef.current += 1;
        candidateKey = intrinsicKey
          ? `${intrinsicKey}-${generatedMessageKeyCounterRef.current}`
          : `message-generated-${generatedMessageKeyCounterRef.current}`;
      } while (allocatedKeysRef.current.has(candidateKey));
    }

    allocatedKeysRef.current.add(candidateKey);
    messageKeyMapRef.current.set(message, candidateKey);
    return candidateKey;
  }, []);

  // 单条消息渲染 —— 精简视图下复用同一渲染器(折叠展开后也走它), 不重写消息组件。
  const renderMessage = useCallback((message: ChatMessage, prevMessage: ChatMessage | null) => (
    <MessageComponent
      message={message}
      prevMessage={prevMessage}
      createDiff={createDiff}
      onFileOpen={onFileOpen}
      onShowSettings={onShowSettings}
      onGrantToolPermission={onGrantToolPermission}
      autoExpandTools={autoExpandTools}
      showRawParameters={showRawParameters}
      showThinking={showThinking}
      selectedProject={selectedProject}
      provider={provider}
    />
  ), [createDiff, onFileOpen, onShowSettings, onGrantToolPermission, autoExpandTools, showRawParameters, showThinking, selectedProject, provider]);

  // 精简开启 → 折叠中间工作记录; 关闭 → 每条消息一个显示项(保留原始相邻关系做分组)。
  const displayItems = useMemo<CleanDisplayItem[]>(() => {
    if (!cleanView) {
      return visibleMessages.map((message, idx) => ({
        kind: 'msg' as const,
        message,
        prev: idx > 0 ? visibleMessages[idx - 1] : null,
      }));
    }
    return buildCleanView(visibleMessages);
  }, [cleanView, visibleMessages]);

  return (
    <div
      ref={scrollContainerRef}
      onWheel={onWheel}
      onTouchMove={onTouchMove}
      className="relative flex-1 space-y-3 overflow-y-auto overflow-x-hidden px-0 py-3 sm:space-y-4 sm:p-4"
    >
      {isLoadingSessionMessages && chatMessages.length === 0 ? (
        <div className="mt-8 text-center text-gray-500 dark:text-gray-400">
          <div className="flex items-center justify-center space-x-2">
            <div className="h-4 w-4 animate-spin rounded-full border-b-2 border-gray-400" />
            <p>{t('session.loading.sessionMessages')}</p>
          </div>
        </div>
      ) : chatMessages.length === 0 ? (
        <ProviderSelectionEmptyState
          selectedSession={selectedSession}
          currentSessionId={currentSessionId}
          provider={provider}
          setProvider={setProvider}
          textareaRef={textareaRef}
          claudeModel={claudeModel}
          setClaudeModel={setClaudeModel}
          cursorModel={cursorModel}
          setCursorModel={setCursorModel}
          codexModel={codexModel}
          setCodexModel={setCodexModel}
          geminiModel={geminiModel}
          setGeminiModel={setGeminiModel}
          tasksEnabled={tasksEnabled}
          isTaskMasterInstalled={isTaskMasterInstalled}
          onShowAllTasks={onShowAllTasks}
          setInput={setInput}
        />
      ) : (
        <>
          {/* 精简/详细视图开关(右上, sticky, 低调) —— 学习 codex: 默认只看每轮最后一段文本, 工作记录折叠。
              做小做淡: 平时半透明仅一个字, hover 才明显, 不占视觉空间。 */}
          <div className="pointer-events-none sticky top-0 z-20 flex justify-end pr-1">
            <button
              type="button"
              data-testid="chat-clean-view-toggle"
              aria-pressed={cleanView}
              onClick={() => setCleanView((v) => !v)}
              title={cleanView ? '精简视图: 已折叠中间工作记录。点击看完整过程' : '详细视图: 显示全过程。点击折叠工作记录'}
              className="pointer-events-auto rounded border border-transparent px-1.5 py-0.5 text-[14px] text-gray-400 opacity-60 transition-opacity hover:border-gray-300 hover:bg-white/90 hover:opacity-100 dark:text-gray-500 dark:hover:border-gray-700 dark:hover:bg-gray-900/80"
            >
              {cleanView ? '精简' : '全部'}
            </button>
          </div>

          {/* Loading indicator for older messages (hide when load-all is active) */}
          {isLoadingMoreMessages && !isLoadingAllMessages && !allMessagesLoaded && (
            <div className="py-3 text-center text-gray-500 dark:text-gray-400">
              <div className="flex items-center justify-center space-x-2">
                <div className="h-4 w-4 animate-spin rounded-full border-b-2 border-gray-400" />
                <p className="text-sm">{t('session.loading.olderMessages')}</p>
              </div>
            </div>
          )}

          {/* Indicator showing there are more messages to load (hide when all loaded) */}
          {hasMoreMessages && !isLoadingMoreMessages && !allMessagesLoaded && (
            <div className="border-b border-gray-200 py-2 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
              {totalMessages > 0 && (
                <span>
                  {t('session.messages.showingOf', { shown: sessionMessagesCount, total: totalMessages })}{' '}
                  <span className="text-sm">{t('session.messages.scrollToLoad')}</span>
                </span>
              )}
            </div>
          )}

          {/* Floating "Load all messages" overlay */}
          {(showLoadAllOverlay || isLoadingAllMessages || loadAllJustFinished) && (
            <div className="pointer-events-none sticky top-2 z-20 flex justify-center">
              {loadAllJustFinished ? (
                <div className="flex items-center space-x-2 rounded-full bg-green-600 px-4 py-1.5 text-sm font-medium text-white shadow-lg dark:bg-green-500">
                  <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>{t('session.messages.allLoaded')}</span>
                </div>
              ) : (
                <button
                  className="pointer-events-auto flex items-center space-x-2 rounded-full bg-blue-600 px-4 py-1.5 text-sm font-medium text-white shadow-lg transition-all duration-200 hover:scale-105 hover:bg-blue-700 disabled:cursor-wait disabled:opacity-75 dark:bg-blue-500 dark:hover:bg-blue-600"
                  onClick={loadAllMessages}
                  disabled={isLoadingAllMessages}
                >
                  {isLoadingAllMessages && (
                    <div className="h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  )}
                  <span>
                    {isLoadingAllMessages
                      ? t('session.messages.loadingAll')
                      : <>{t('session.messages.loadAll')} {totalMessages > 0 && `(${totalMessages})`}</>
                    }
                  </span>
                </button>
              )}
            </div>
          )}

          {/* Performance warning when all messages are loaded */}
          {allMessagesLoaded && (
            <div className="border-b border-amber-200 bg-amber-50 py-1.5 text-center text-sm text-amber-600 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
              {t('session.messages.perfWarning')}
            </div>
          )}

          {/* Legacy message count indicator (for non-paginated view) */}
          {!hasMoreMessages && chatMessages.length > visibleMessageCount && (
            <div className="border-b border-gray-200 py-2 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
              {t('session.messages.showingLast', { count: visibleMessageCount, total: chatMessages.length })} |
              <button className="ml-1 text-blue-600 underline hover:text-blue-700" onClick={loadEarlierMessages}>
                {t('session.messages.loadEarlier')}
              </button>
              {' | '}
              <button
                className="text-blue-600 underline hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                onClick={loadAllMessages}
              >
                {t('session.messages.loadAll')}
              </button>
            </div>
          )}

          {displayItems.map((item) => {
            if (item.kind === 'fold') {
              return <WorkFold key={item.id} messages={item.messages} renderMessage={renderMessage} />;
            }
            return (
              <Fragment key={getMessageKey(item.message)}>
                {renderMessage(item.message, item.prev)}
              </Fragment>
            );
          })}
          {messagesFooter}
        </>
      )}
    </div>
  );
}

