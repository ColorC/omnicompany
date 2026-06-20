import type { ReactNode } from 'react';
import type { Project, ProjectSession, LLMProvider } from '../../../types/app';

export type Provider = LLMProvider;

export type PermissionMode = 'default' | 'acceptEdits' | 'auto' | 'bypassPermissions' | 'plan';

export interface ChatImage {
  data: string;
  name: string;
}

export interface ToolResult {
  content?: unknown;
  isError?: boolean;
  timestamp?: string | number | Date;
  toolUseResult?: unknown;
  [key: string]: unknown;
}

export interface SubagentChildTool {
  toolId: string;
  toolName: string;
  toolInput: unknown;
  toolResult?: ToolResult | null;
  timestamp: Date;
}

export interface ChatMessage {
  id?: string | number;
  type: string;
  content?: string;
  timestamp: string | number | Date;
  images?: ChatImage[];
  reasoning?: string;
  isThinking?: boolean;
  isStreaming?: boolean;
  isInteractivePrompt?: boolean;
  isContextNotification?: boolean;
  isToolUse?: boolean;
  toolName?: string;
  toolInput?: unknown;
  toolResult?: ToolResult | null;
  toolId?: string;
  toolCallId?: string;
  isSubagentContainer?: boolean;
  subagentState?: {
    childTools: SubagentChildTool[];
    currentToolIndex: number;
    isComplete: boolean;
  };
  [key: string]: unknown;
}

export interface ClaudeSettings {
  allowedTools: string[];
  disallowedTools: string[];
  skipPermissions: boolean;
  projectSortOrder: string;
  lastUpdated?: string;
  [key: string]: unknown;
}

export interface ClaudePermissionSuggestion {
  toolName: string;
  entry: string;
  isAllowed: boolean;
}

export interface PermissionGrantResult {
  success: boolean;
  alreadyAllowed?: boolean;
  updatedSettings?: ClaudeSettings;
}

export interface PendingPermissionRequest {
  requestId: string;
  toolName: string;
  input?: unknown;
  context?: unknown;
  sessionId?: string | null;
  receivedAt?: Date;
}

export interface QuestionOption {
  label: string;
  description?: string;
}

export interface Question {
  question: string;
  header?: string;
  options: QuestionOption[];
  multiSelect?: boolean;
}

export type SessionNavigationOptions = {
  replace?: boolean;
};

export interface ChatInterfaceProps {
  selectedProject: Project | null;
  selectedSession: ProjectSession | null;
  ws: WebSocket | null;
  sendMessage: (message: unknown) => void;
  latestMessage: any;
  onFileOpen?: (filePath: string, diffInfo?: any) => void;
  onInputFocusChange?: (focused: boolean) => void;
  onSessionActive?: (sessionId?: string | null) => void;
  onSessionInactive?: (sessionId?: string | null) => void;
  onSessionProcessing?: (sessionId?: string | null) => void;
  onSessionAwaitingPermission?: (sessionId?: string | null) => void;
  onSessionNotProcessing?: (sessionId?: string | null) => void;
  onSessionPreview?: (sessionId: string, preview: string) => void;
  processingSessions?: Set<string>;
  onReplaceTemporarySession?: (sessionId?: string | null) => void;
  onNavigateToSession?: (targetSessionId: string, options?: SessionNavigationOptions) => void;
  onShowSettings?: () => void;
  autoExpandTools?: boolean;
  showRawParameters?: boolean;
  showThinking?: boolean;
  autoScrollToBottom?: boolean;
  sendByCtrlEnter?: boolean;
  externalMessageUpdate?: number;
  newSessionTrigger?: number;
  onTaskClick?: (...args: unknown[]) => void;
  onShowAllTasks?: (() => void) | null;
  /** 本地(前端动作)斜杠命令: 进菜单 + 命中走 onLocalCommand(总控 /compact /new)。 */
  localCommands?: Array<{ name: string; description?: string; local?: boolean; [k: string]: unknown }>;
  onLocalCommand?: (name: string) => void;
  /** 精简视图默认值(总控对话默认 true): 折叠中间工作记录, 只显示每轮最后一段文本。 */
  cleanViewDefault?: boolean;
  /** 设了就把精简/详细偏好按这个 key 持久化(如 'controller')。 */
  cleanViewKey?: string;
  /** 渲染在消息列表末尾(对话最后)的附加内容, 如"本对话新材料"卡片。 */
  messagesFooter?: ReactNode;
}
