/**
 * CcChatPanel wraps the upstream-style ChatInterface around an OmniChat session.
 *
 * Responsibilities:
 * 1. Keep the WebSocket connected and replay snapshots after reconnects.
 * 2. Convert each backend legacy frame into normalized ChatInterface messages.
 * 3. Pass same-frame messages as one ordered batch so status/result/stream-end
 *    events cannot be interleaved by delayed client-side timers.
 * 4. Adapt the CcSession entity into the Project and ProjectSession props that
 *    ChatInterface expects.
 */

import React, { useCallback, useMemo, useState } from 'react'

import ChatInterface from '../../components/chat/view/ChatInterface'
import { PaletteOpsProvider } from '../../contexts/PaletteOpsContext'
// @ts-ignore — jsx 文件没 .d.ts
import { TasksSettingsProvider } from '../../contexts/TasksSettingsContext'
import { ccChatApi } from '../../api/ccChatClient'
import { useWsAutoReconnect } from '../../lib/wsAutoReconnect'
import {
  composerSendToWsFrame,
  entityToProject,
  entityToSession,
} from '../../lib/ccSessionAdapter'
import CollapsibleSessionContext from './CollapsibleSessionContext'
import type { CcSessionEntity } from './index'


interface Props {
  entity: CcSessionEntity
  /** true = 也渲染右侧 SessionContextPanel (active plan / 工具调用 / 修改记录). 默认 false. */
  showContextPanel?: boolean
  /** session 切到 "正在响应" 状态时 (LLM 输出中). 给 VSCode 扩展上报 tab 状态用. */
  onSessionProcessing?: (sessionId?: string | null) => void
  onSessionAwaitingPermission?: (sessionId?: string | null) => void
  /** session 切回闲置状态时. */
  onSessionNotProcessing?: (sessionId?: string | null) => void
  /** 本地斜杠命令拦截(fallback: 用户输入 /xxx 发送时先过这里): 返回 true = 已本地处理, 不发给 LLM。 */
  onSlashCommand?: (raw: string) => boolean
  /** 本地(前端动作)斜杠命令: 进 composer 斜杠菜单 + 命中走 onLocalCommand(总控 /compact /new)。 */
  localCommands?: Array<{ name: string; description?: string; local?: boolean; [k: string]: unknown }>
  onLocalCommand?: (name: string) => void
  /** 精简视图默认值(总控对话传 true): 折叠中间工作记录, 只显示每轮最后一段文本。 */
  cleanViewDefault?: boolean
  /** 精简/详细偏好持久化 key(如 'controller')。 */
  cleanViewKey?: string
  /** 渲染在对话末尾的附加内容(如"本对话新材料"卡片)。 */
  messagesFooter?: React.ReactNode
}

type VscodeSessionState = 'processing' | 'awaiting_permission' | 'idle' | 'ended'

function postToOmniHost(message: Record<string, unknown>) {
  const payload = { __omnichat: true, ...message }
  try {
    window.parent?.postMessage(payload, '*')
  } catch { /* browser / sandbox fallback */ }
  try {
    if (window.top && window.top !== window.parent) {
      window.top.postMessage(payload, '*')
    }
  } catch { /* browser / sandbox fallback */ }
}


function CcChatPanelInner({
  entity,
  showContextPanel = false,
  onSessionProcessing,
  onSessionAwaitingPermission,
  onSessionNotProcessing,
  onSlashCommand,
  localCommands,
  onLocalCommand,
  cleanViewDefault,
  cleanViewKey,
  messagesFooter,
}: Props) {
  // ChatInterface consumes either one normalized message or an ordered batch.
  const [latestMessage, setLatestMessage] = useState<any>(null)

  // Processing state stays single-sourced inside ChatInterface:
  // send -> useChatComposerState; complete/error -> useChatRealtimeHandlers.
  // 聊天去返回: 后端 ccdaemon 现在直发上游 wire NormalizedMessage。
  // 前端直接喂 ChatInterface。
  const handleFrame = useCallback((ev: MessageEvent) => {
    let frame: any
    try { frame = JSON.parse(ev.data as string) } catch { return }
    if (!frame || typeof frame !== 'object') return

    // snapshot: 后端发 {kind:'snapshot', messages:[wire NM], tokenUsage}。messages 已是
    // wire NM(_append_event_history 产出), 批量喂; tokenUsage 转一条 status。历史另有
    // /history REST 兜底(complete 时 refreshFromServer)。
    if (frame.kind === 'snapshot') {
      const batch: any[] = Array.isArray(frame.messages) ? [...frame.messages] : []
      if (frame.tokenUsage) {
        batch.push({ kind: 'status', text: 'token_budget', tokenBudget: frame.tokenUsage })
      }
      if (batch.length) setLatestMessage(batch.length === 1 ? batch[0] : batch)
      return
    }

    // 其余 = 后端直发的扁平 wire NormalizedMessage, 直接喂(useSessionStore/handlers 本就是上游消费器)
    setLatestMessage(frame)
  }, [])

  const wsConn = useWsAutoReconnect({
    url: ccChatApi.wsUrl(entity.id),
    onMessage: handleFrame,
  })

  // ChatComposer 发 {type:'claude-command', command, options}, backend chat.py 期望
  // {type:'user.message', content}. composerSendToWsFrame 翻译 ChatComposer payload
  // → backend ws frame. 返 null 表静默丢弃 (例 check-session-status 等控制帧 backend
  // 还没实现 — 不发就不会触发 backend 的 unknown_frame_type 错误回包).
  // **不在这里 fire onSessionProcessing** — useChatComposerState.handleSubmit 已经触
  // 过一次, 这里再触会让 wrapper 的 postMessage 发 2x ('processing' 重复).
  const sendMessage = useCallback((message: unknown) => {
    // 本地斜杠命令拦截(总控 /compact /new 等前端动作): composer 发的是 {type:'*-command', command:'/xxx'}。
    // 命中则本地处理、不发给 LLM。
    const m = message as any
    if (
      onSlashCommand &&
      m && typeof m.type === 'string' && m.type.endsWith('-command') &&
      typeof m.command === 'string' && m.command.trim().startsWith('/')
    ) {
      if (onSlashCommand(m.command)) return
    }
    const payload = composerSendToWsFrame(message)
    if (payload === null) return
    wsConn.send(payload)
  }, [wsConn, onSlashCommand])

  const openFileInHost = useCallback((filePath: string) => {
    const trimmed = String(filePath || '').trim()
    if (!trimmed) return
    const isAbsolute = /^[A-Za-z]:[\\/]/.test(trimmed) || trimmed.startsWith('/') || trimmed.startsWith('\\\\')
    const path = isAbsolute ? trimmed : `${entity.cwd.replace(/[\\/]+$/, '')}\\${trimmed}`
    try {
      postToOmniHost({ type: 'open-file', path })
    } catch { /* browser fallback: no host bridge */ }
  }, [entity.cwd])

  // entity → ChatInterface 必填 props (selectedProject / selectedSession).
  // 必须 useMemo 稳定引用, 否则下游 useEffect dep 看新引用每次 render 都 refire
  // (token-usage 端点反复 fetch + setTokenBudget(stub 0) 把真值覆盖, 用户 2026-05-12 撞).
  const project = useMemo(() => entityToProject(entity), [entity.id, entity.cwd, entity.alive])
  const session = useMemo(() => entityToSession(entity), [entity.id, entity.cwd, entity.alive, entity.title, entity.startedAt, entity.provider])

  // #2 接管/交还(仅采纳来的会话显示)。乐观更新, 失败回滚。
  const [takenOver, setTakenOver] = useState(!!entity.takenOver)
  const toggleTakeover = useCallback(async () => {
    const next = !takenOver
    setTakenOver(next)
    try { await ccChatApi.takeover(entity.id, next) } catch { setTakenOver(!next) }
  }, [takenOver, entity.id])

  // N2b 推理强度: 交互聊天用上游已有的 ThinkingModeSelector(思考模式: 标准→Ultrathink),
  // 不再自造 effort 下拉(用户 2026-06-07 反馈"用完善的已有组件")。SDK effort 选项仍保留,
  // 但只给无 composer UI 的 headless subagent(spawn/workflow/convos adopt)走 CLI/API 设。

  // ChatInterface 在 wsConn.state !== 'connected' 时会显示 connecting 状态
  // (它内部用 ws 引用 + readyState 判断). 这里我们把 wsConn.ws 暴露出去.
  return (
    <div
      style={{ display: 'flex', flex: 1, minWidth: 0, height: '100%' }}
      data-cc-chat-panel
      data-cc-chat-session-id={entity.id}
      data-cc-provider={(entity as any).provider || 'claude_code'}
    >
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {entity.adopted && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 10px', background: takenOver ? '#3a1d1d' : '#10233a', borderBottom: '1px solid #263443', color: '#cdd9e5', fontSize: 14, flexShrink: 0 }}>
            <span style={{ color: '#9fd0ff', fontWeight: 600 }}>采纳的会话</span>
            <span style={{ color: '#8b949e' }}>{takenOver ? '你已接管 · 总控不自动 hook' : '总控驱动中 · 完成后总控秘书式 review 齐全度并交审阅台'}</span>
            <span style={{ flex: 1 }} />
            <button type="button" data-testid="cc-takeover-toggle" onClick={() => { void toggleTakeover() }} style={{ border: '1px solid #2f81f7', background: '#10233a', color: '#79c0ff', borderRadius: 4, padding: '2px 12px', cursor: 'pointer', fontSize: 14 }}>
              {takenOver ? '交还给总控' : '接管对话'}
            </button>
          </div>
        )}
        <ChatInterface
          selectedProject={project}
          selectedSession={session}
          ws={wsConn.ws}
          sendMessage={sendMessage}
          latestMessage={latestMessage}
          onFileOpen={openFileInHost}
          onSessionProcessing={onSessionProcessing}
          onSessionAwaitingPermission={onSessionAwaitingPermission}
          onSessionNotProcessing={onSessionNotProcessing}
          onSessionPreview={(sessionId, preview) => {
            postToOmniHost({ type: 'session-preview', sessionId, preview })
          }}
          autoExpandTools={false}
          showRawParameters={false}
          showThinking={true}
          autoScrollToBottom={true}
          sendByCtrlEnter={true}
          localCommands={localCommands}
          onLocalCommand={onLocalCommand}
          cleanViewDefault={cleanViewDefault}
          cleanViewKey={cleanViewKey}
          messagesFooter={messagesFooter}
        />
      </div>
      {showContextPanel && (
        <CollapsibleSessionContext sessionId={entity.id} alive={entity.alive} />
      )}
    </div>
  )
}


export default function CcChatPanel(props: Props) {
  // VSCode 薄壳扩展嵌 iframe 时, 我们 postMessage 上报 session 状态让扩展更新
  // tab 标题. 浏览器直接打开 chat-standalone 时 window === window.top, postMessage
  // 给自己就是 no-op, 不影响.
  const postSessionState = React.useCallback((state: VscodeSessionState, sid: string | null) => {
    try {
      postToOmniHost({ type: 'session-state', sessionId: sid, state })
    } catch { /* SSR / sandbox 等 */ }
  }, [])

  React.useEffect(() => {
    const preview = (props.entity.title || props.entity.id.slice(-6)).trim()
    try {
      postToOmniHost({ type: 'session-preview', sessionId: props.entity.id, preview })
      postSessionState(props.entity.alive ? 'idle' : 'ended', props.entity.id)
    } catch { /* browser fallback: no host bridge */ }
  }, [props.entity.alive, props.entity.id, props.entity.title, postSessionState])

  const handleProc = React.useCallback((sid?: string | null) => {
    postSessionState('processing', sid || null)
  }, [postSessionState])
  const handleAwaiting = React.useCallback((sid?: string | null) => {
    postSessionState('awaiting_permission', sid || null)
  }, [postSessionState])
  const handleNotProc = React.useCallback((sid?: string | null) => {
    postSessionState('idle', sid || null)
  }, [postSessionState])
  // session 切换 / 卸载时通知 ended (entity.alive=false 也通知)
  React.useEffect(() => {
    if (!props.entity.alive) {
      postSessionState('ended', props.entity.id)
    }
    return () => {
      // 组件卸载不主动发 ended — 切 session 是新 mount, 旧 ended 不一定是真结束
    }
  }, [props.entity.alive, props.entity.id, postSessionState])

  // ChatInterface 内部用 usePaletteOps + useTasksSettings + (可选) PermissionContext.
  // 包必要 Provider — ThemeProvider 由外层 (ChatStandalone) 已经包了, 这里不重复.
  return (
    <PaletteOpsProvider>
      <TasksSettingsProvider>
        <CcChatPanelInner
          {...props}
          onSessionProcessing={(sid) => { handleProc(sid); props.onSessionProcessing?.(sid) }}
          onSessionAwaitingPermission={(sid) => { handleAwaiting(sid); props.onSessionAwaitingPermission?.(sid) }}
          onSessionNotProcessing={(sid) => { handleNotProc(sid); props.onSessionNotProcessing?.(sid) }}
        />
      </TasksSettingsProvider>
    </PaletteOpsProvider>
  )
}
