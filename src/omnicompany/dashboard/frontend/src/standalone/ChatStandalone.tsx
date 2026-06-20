/**
 * ChatStandalone — 裸聊天根组件 (无 ActivityBar / Sidebar / EditorArea 外壳).
 *
 * 用途: 浏览器或 VSCode Simple Browser 嵌入时直接看 chat, 不带 IDE 形态外壳.
 * URL: /chat-standalone (FastAPI 路由 → SPA bundle → main.tsx pathname 分流到本组件)
 *
 * URL 参数:
 *   ?session=chat-xxx  — 直接挂载指定 session (VSCode reload tab 续上)
 *
 * Reuses CcChatPanel + ccChatApi, matching the dashboard embedded chat path.
 *
 * data-testid="chat-standalone-root" — Playwright e2e 抓的稳定 selector.
 */

import React, { useCallback, useEffect, useState } from 'react'
import { PanelLeftOpen } from 'lucide-react'
import { ccChatApi, type CcChatSessionMeta, type CcChatProvider } from '../api/ccChatClient'
import CcChatPanel from '../entities/cc_session/CcChatPanel'
import type { CcSessionEntity } from '../entities/cc_session/index'
import ChatStandaloneSidebar from './ChatStandaloneSidebar'
// CodexLogo / CursorLogo / DarkModeToggle 等 deps useTheme(), 必须有 ThemeProvider
// 包裹. dashboard 完整外壳已经在 App 之上有 (上层 wrapper), 但 ChatStandalone 是
// 平行根组件需要自己包.
// @ts-ignore — jsx 文件没 .d.ts
import { ThemeProvider } from '../contexts/ThemeContext'
import { CLAUDE_MODELS, CODEX_MODELS } from '../shared/modelConstants'
import { colors, fonts, fontSize, radius, spacing } from '../shell/tokens'

function postToOmniHost(message: Record<string, unknown>) {
  const payload = { __omnichat: true, ...message }
  let posted = false
  try {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage(payload, '*')
      posted = true
    }
  } catch { /* browser / sandbox fallback */ }
  try {
    if (window.top && window.top !== window && window.top !== window.parent) {
      window.top.postMessage(payload, '*')
      posted = true
    }
  } catch { /* browser / sandbox fallback */ }
  return posted
}


// standalone 路径强制深色 — 不让 localStorage 之前的 'light' 设置 (老 bug 残留)
// 把页面带回 light. ThemeProvider 启动前清残留, 然后 ThemeProvider 默认逻辑会走 dark.
function forceDarkBeforeMount() {
  try {
    const cur = localStorage.getItem('theme')
    if (cur === 'light') localStorage.removeItem('theme')
    document.documentElement.classList.add('dark')
  } catch { /* SSR / privacy mode 等环境兜底 */ }
}
forceDarkBeforeMount()

const S: Record<string, React.CSSProperties> = {
  root: { position: 'relative', display: 'flex', height: '100vh', overflow: 'hidden', background: colors.bg, color: colors.text, fontFamily: fonts.ui, fontSize: fontSize.body, letterSpacing: 0 },
  body: { flex: 1, minHeight: 0, display: 'flex' },
  empty: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: spacing.md, color: colors.textMuted },
  sidebarRestore: {
    position: 'absolute',
    top: 8,
    left: 8,
    zIndex: 40,
    width: 32,
    height: 32,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: `1px solid ${colors.border}`,
    borderRadius: radius.default,
    background: colors.bgCard,
    color: colors.textMuted,
    cursor: 'pointer',
    boxShadow: '0 10px 24px rgba(0, 0, 0, 0.34)',
  },
}

function metaToEntity(m: CcChatSessionMeta): CcSessionEntity {
  const title = m.name && m.name.trim() ? m.name.trim() : m.id.slice(-6)
  return {
    type: 'cc_session',
    kind: 'chat',
    id: m.id,
    title,
    cwd: m.cwd,
    alive: m.alive,
    status: m.alive ? 'alive' : 'ended',
    cmd: m.cmd,
    startedAt: m.started_at,
    claudeSessionId: m.claude_session_id,
    activePlan: m.active_plan || null,
    provider: m.provider || 'claude_code',
    tags: ['chat', m.alive ? 'alive' : 'ended'],
  }
}

// Provider + model 候选 — 新建 session 用. Model 列表来自 ccChatClient 注释 (claude
// 系) + omni_agent 跑 qwen-3.6-plus / codex 各自模型. 实际 model 字段 backend 透传给
// provider, 各 provider 自己解释.
// 2026-05-26: controller 拍前面让新建对话时更容易选到 BOSS SIGHT 总控
const PROVIDER_OPTIONS: Array<{ value: CcChatProvider; label: string }> = [
  { value: 'controller', label: 'BOSS SIGHT 总控' },
  { value: 'claude_code', label: 'Claude Code (订阅)' },
  { value: 'omni_agent', label: 'OmniAgent (本地 qwen)' },
  { value: 'codex', label: 'Codex (OpenAI)' },
]

// 各 provider 推荐的 model 短名 + 具体版本 (用户可选短名让 SDK 走默认版本, 或选具体
// 版本号精确控制). 短名 (sonnet/opus/haiku) SDK 解析后用 ~/.claude/settings.json 的
// 默认版本. 具体 ID (claude-opus-4-7 等) 直接覆盖.
const MODEL_BY_PROVIDER: Record<CcChatProvider, string[]> = {
  claude_code: [
    '(默认)',
    'claude-opus-4-7',
    'claude-opus-4-6',
    'claude-sonnet-4-6',
    'claude-haiku-4-5',
    'sonnet', 'opus', 'haiku', 'opusplan', 'sonnet[1m]',
  ],
  omni_agent: ['(默认)', 'qwen-3.6-plus', 'deepseek-v4-pro'],
  codex: ['(默认)', 'gpt-5', 'gpt-5-codex', 'o3', 'o4-mini'],
  // 总控走 omnicompany AgentNodeLoop → LLMCallRouter → the_company 聚合 API
  // (统一抽象, U-032). the_company 支持所有 claude / gpt / qwen 模型,
  // 默认 claude-opus-4-7 (用户原始需求 §2.2 默认 400k ctx).
  controller: [
    'claude-opus-4-7',
    'claude-opus-4-6',
    'claude-sonnet-4-6',
    'gpt-5.4',
    'gpt-5.3-codex',
    'qwen3.6-plus',
  ],
}

// 内层组件 — 真业务逻辑. 外层 ChatStandalone 仅包 ThemeProvider.
function ChatStandaloneInner() {
  const [sessions, setSessions] = useState<CcChatSessionMeta[] | null>(null)
  const [sessionTotal, setSessionTotal] = useState(0)
  const [sessionHasMore, setSessionHasMore] = useState(false)
  const [sessionSearch, setSessionSearch] = useState('')
  const [sessionFullText, setSessionFullText] = useState(false)
  const [showArchived, setShowArchived] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 新建 session 时选的 provider + model
  // 2026-05-26: 新建会话默认 provider=controller (BOSS SIGHT 总控), 用户原话
  // "我创建 bosssight 对话" 即默认入口.
  // URL `?provider=<x>` 可锁定 provider (嵌入方加 ?provider=controller
  // → sidebar 只显示该 provider 的 session + 新建强制为该 provider).
  const providerLock: CcChatProvider | null = (() => {
    try {
      const p = new URLSearchParams(window.location.search).get('provider')
      if (p === 'controller' || p === 'claude_code' || p === 'codex' || p === 'omni_agent') {
        return p as CcChatProvider
      }
    } catch { /* */ }
    return null
  })()
  const [newProvider, setNewProvider] = useState<CcChatProvider>(providerLock || 'controller')
  const [newModel, setNewModel] = useState<string>('(默认)')
  // 右侧上下文面板切换 — 默认隐藏 (vscode 窄窗体验), 可手动唤出
  const [showContextPanel, setShowContextPanel] = useState<boolean>(false)
  const [sidebarVisible, setSidebarVisible] = useState(true)
  // 初次加载: 只在 URL 显式带 ?session=xxx 时挂上对应 session.
  // 不再"自动选最新 alive" — 那条逻辑会让浏览器进 chat-standalone 直接显示上一次留下
  // 的 session 历史 (用户 2026-05-13 e2e 实测看到 12 条遗留消息), 紧接着用户点
  // "+ 新 session" 会触发 entity 切换 → CcChatPanel remount → 2 个 ws 实例.
  // 没 URL hint 时显示 empty state, 让用户主动点 "+ 新 session" 或选下拉.
  // VSCode 扩展打开 tab 时只要把上次 sticky 的 session id 拼进 ?session= 就能续, 不靠
  // 服务端 latest-alive 兜底.
  const pageSize = 60

  const refresh = async (autoSelect: boolean, append = false) => {
    try {
      const selectedFromUrl = new URLSearchParams(window.location.search).get('session')
      const offset = append ? (sessions?.length || 0) : 0
      const result = await ccChatApi.listPage({
        q: sessionSearch.trim(),
        fullText: sessionFullText,
        limit: pageSize,
        offset,
        pinnedId: selectedId || selectedFromUrl,
        includeArchived: showArchived,
      })
      const list = result.items || []
      setSessions((prev) => append ? [...(prev || []), ...list.filter((s) => !(prev || []).some((p) => p.id === s.id))] : list)
      setSessionTotal(result.total)
      setSessionHasMore(result.has_more)
      if (autoSelect) {
        const params = new URLSearchParams(window.location.search)
        const want = params.get('session')
        if (want && list.some((s) => s.id === want)) {
          setSelectedId(want)
        }
        // else: 不自动选 — 等用户操作
      }
    } catch (e) {
      setError(`list 失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  useEffect(() => { void refresh(true) }, [])

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void refresh(false)
    }, 250)
    return () => window.clearTimeout(handle)
  }, [sessionSearch, sessionFullText, showArchived])

  useEffect(() => {
    if (sessions === null) return
    const url = new URL(window.location.href)
    if (selectedId) url.searchParams.set('session', selectedId)
    else url.searchParams.delete('session')
    window.history.replaceState({}, '', url.toString())
  }, [selectedId, sessions])

  const onCreate = async () => {
    setCreating(true)
    setError(null)
    try {
      const body: { provider?: CcChatProvider; model?: string } = { provider: newProvider }
      if (newModel && newModel !== '(默认)') body.model = newModel
      const m = await ccChatApi.create(body)
      await refresh(false)
      setSelectedId(m.id)
    } catch (e) {
      setError(`create 失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setCreating(false)
    }
  }

  const selected = sessions?.find((s) => s.id === selectedId) || null
  const entity = selected ? metaToEntity(selected) : null

  const persistSessionName = useCallback(async (sessionId: string, nextName: string) => {
    try {
      const result = await ccChatApi.rename(sessionId, nextName)
      const savedName = result.name || ''
      setSessions((prev) => prev?.map((s) =>
        s.id === sessionId ? { ...s, name: savedName } : s,
      ) || prev)
      postToOmniHost({
        type: 'session-preview',
        sessionId,
        preview: savedName.trim() || sessionId.slice(-6),
      })
    } catch (err) {
      setError(`rename 失败: ${err instanceof Error ? err.message : String(err)}`)
      void refresh(false)
    }
  }, [])

  const patchSessionMetadata = useCallback(async (
    sessionId: string,
    patch: { archived?: boolean; favorite?: boolean },
  ) => {
    const prevSessions = sessions
    setSessions((prev) => prev?.map((s) =>
      s.id === sessionId ? { ...s, ...patch } : s,
    ) || prev)
    if (patch.archived === true && selectedId === sessionId && !showArchived) {
      setSelectedId(null)
    }
    try {
      const saved = await ccChatApi.patchMetadata(sessionId, patch)
      setSessions((prev) => prev?.map((s) =>
        s.id === sessionId ? { ...s, archived: saved.archived, favorite: saved.favorite } : s,
      ) || prev)
    } catch (err) {
      setError(`metadata 失败: ${err instanceof Error ? err.message : String(err)}`)
      setSessions(prevSessions)
      void refresh(false)
    }
  }, [sessions, selectedId, showArchived])

  useEffect(() => {
    if (!selected) return
    const preview = (selected.name && selected.name.trim()) ? selected.name.trim() : selected.id.slice(-6)
    postToOmniHost({ type: 'session-preview', sessionId: selected.id, preview })
  }, [selected?.id, selected?.name])

  return (
    <div style={S.root} data-testid="chat-standalone-root">
      {!sidebarVisible && (
        <button
          type="button"
          style={S.sidebarRestore}
          onClick={() => setSidebarVisible(true)}
          title="展开侧边栏"
          data-testid="chat-sidebar-expand"
        >
          <PanelLeftOpen size={16} />
        </button>
      )}
      {/* 2026-05-26: 右上角"进驾驶舱"快捷入口.
          检测被 iframe 嵌入用 ?embedded=1 URL 参数 (不用 window.parent
          因为 VSCode webview iframe 也会 trigger 那个判断 → 按钮被错误隐藏). */}
      {(typeof window === 'undefined' || !new URLSearchParams(window.location.search).has('embedded')) && (
        <a
          href="/"
          title="打开 BOSS SIGHT 审阅台"
          data-testid="open-boss-sight-cockpit"
          style={{
            position: 'absolute', top: 8, right: 12, zIndex: 40,
            padding: '6px 12px', borderRadius: 4,
            background: '#1c2c45', color: '#58a6ff',
            border: '1px solid #30363d',
            textDecoration: 'none', fontSize: 14, fontWeight: 600,
          }}
        >
          🎛 BOSS SIGHT 审阅台 →
        </a>
      )}
      <div style={S.body}>
        {sidebarVisible && (
          <ChatStandaloneSidebar
            sessions={providerLock
              ? (sessions || []).filter((s) => (s.provider || 'claude_code') === providerLock)
              : sessions}
            selectedId={selectedId}
            total={sessionTotal}
            hasMore={sessionHasMore}
            search={sessionSearch}
            fullText={sessionFullText}
            showArchived={showArchived}
            creating={creating}
            error={error}
            newProvider={newProvider}
            newModel={newModel}
            providerOptions={providerLock
              ? PROVIDER_OPTIONS.filter((o) => o.value === providerLock)
              : PROVIDER_OPTIONS}
            modelOptions={newProvider === 'codex' ? ['(默认)', ...CODEX_MODELS.OPTIONS.map((m: { value: string }) => m.value)] : MODEL_BY_PROVIDER[newProvider]}
            onSearchChange={setSessionSearch}
            onFullTextChange={setSessionFullText}
            onShowArchivedChange={setShowArchived}
            onProviderChange={(provider) => {
              setNewProvider(provider)
              setNewModel('(默认)')
            }}
            onModelChange={setNewModel}
            onSelect={setSelectedId}
            onCreate={() => { void onCreate() }}
            onRefresh={() => { void refresh(false) }}
            onLoadMore={() => { void refresh(false, true) }}
            onRename={(sessionId, name) => { void persistSessionName(sessionId, name) }}
            onArchive={(sessionId, archived) => { void patchSessionMetadata(sessionId, { archived }) }}
            onFavorite={(sessionId, favorite) => { void patchSessionMetadata(sessionId, { favorite }) }}
            onCollapse={() => setSidebarVisible(false)}
          />
        )}
        <div style={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex' }}>
          {entity ? (
            <CcChatPanel key={entity.id} entity={entity} showContextPanel={showContextPanel} />
          ) : (
            <div style={S.empty}>
              <div>没有选中 session</div>
              {sessions && sessions.length === 0 && <div style={{ fontSize: fontSize.caption }}>从左侧新建会话</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ChatStandalone() {
  return (
    <ThemeProvider>
      <ChatStandaloneInner />
    </ThemeProvider>
  )
}
