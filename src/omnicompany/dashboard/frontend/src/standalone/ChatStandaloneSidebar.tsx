import React, { useEffect, useMemo, useState } from 'react'
import {
  Archive,
  ChevronDown,
  ChevronRight,
  Folder,
  GitBranch,
  List,
  MessageSquare,
  PanelLeftClose,
  Plus,
  RefreshCw,
  Search,
  Star,
} from 'lucide-react'
import type { CcChatProvider, CcChatSessionMeta } from '../api/ccChatClient'
import { colors, fonts, fontSize, radius, spacing } from '../shell/tokens'

type ViewMode = 'plan' | 'folder' | 'conversation'

type PlanItem = {
  id: string
  topic?: string
  category?: string
  folder_path?: string
  archived?: boolean
  meta?: Record<string, unknown>
}

type Props = {
  sessions: CcChatSessionMeta[] | null
  selectedId: string | null
  total: number
  hasMore: boolean
  search: string
  fullText: boolean
  showArchived: boolean
  creating: boolean
  error: string | null
  newProvider: CcChatProvider
  newModel: string
  providerOptions: Array<{ value: CcChatProvider; label: string }>
  modelOptions: string[]
  onSearchChange: (value: string) => void
  onFullTextChange: (value: boolean) => void
  onShowArchivedChange: (value: boolean) => void
  onProviderChange: (value: CcChatProvider) => void
  onModelChange: (value: string) => void
  onSelect: (sessionId: string) => void
  onCreate: () => void
  onRefresh: () => void
  onLoadMore: () => void
  onRename: (sessionId: string, name: string) => void
  onArchive: (sessionId: string, archived: boolean) => void
  onFavorite: (sessionId: string, favorite: boolean) => void
  onCollapse: () => void
}

const S: Record<string, React.CSSProperties> = {
  root: {
    position: 'relative',
    width: 318,
    minWidth: 260,
    maxWidth: 360,
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    borderRight: `1px solid ${colors.border}`,
    background: colors.bgPanel,
    color: colors.text,
    flexShrink: 0,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.xs,
    padding: `${spacing.sm}px ${spacing.sm}px ${spacing.xs}px`,
  },
  title: { fontWeight: 700, fontSize: fontSize.title, color: colors.text },
  iconButton: {
    width: 28,
    height: 28,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: `1px solid ${colors.border}`,
    background: colors.bgCard,
    color: colors.textMuted,
    borderRadius: radius.default,
    cursor: 'pointer',
    flexShrink: 0,
  },
  iconButtonActive: { color: colors.accent, borderColor: colors.accent, background: colors.bg },
  createPopover: {
    position: 'absolute',
    top: 44,
    left: spacing.sm,
    right: spacing.sm,
    zIndex: 30,
    display: 'grid',
    gap: spacing.xs,
    padding: spacing.sm,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.default,
    background: colors.bg,
    boxShadow: '0 14px 36px rgba(0, 0, 0, 0.42)',
  },
  createRow: { display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: spacing.xs, alignItems: 'center' },
  select: {
    width: '100%',
    minWidth: 0,
    height: 30,
    background: colors.bgPanel,
    color: colors.text,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.default,
    padding: '0 8px',
    fontSize: fontSize.caption,
    fontFamily: fonts.ui,
  },
  tabs: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: spacing.xs, padding: `${spacing.xs}px ${spacing.sm}px 0` },
  tab: {
    height: 30,
    border: `1px solid ${colors.border}`,
    background: colors.bg,
    color: colors.textMuted,
    borderRadius: radius.default,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    cursor: 'pointer',
    fontSize: fontSize.caption,
    fontFamily: fonts.ui,
  },
  tabActive: { background: colors.bgCard, color: colors.accent },
  searchBox: {
    margin: spacing.sm,
    height: 34,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '0 10px',
    background: colors.bg,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.default,
  },
  searchInput: {
    flex: 1,
    minWidth: 0,
    border: 'none',
    outline: 'none',
    background: 'transparent',
    color: colors.text,
    fontFamily: fonts.ui,
    fontSize: fontSize.body,
  },
  toggles: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    padding: `0 ${spacing.sm}px ${spacing.xs}px`,
    color: colors.textMuted,
    fontSize: fontSize.caption,
  },
  scroll: { flex: 1, minHeight: 0, overflowY: 'auto', padding: `${spacing.xs}px ${spacing.sm}px ${spacing.sm}px` },
  group: { marginBottom: spacing.xs },
  groupButton: {
    width: '100%',
    minHeight: 34,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    border: 'none',
    background: 'transparent',
    color: colors.text,
    borderRadius: radius.default,
    padding: '4px 6px',
    cursor: 'pointer',
    textAlign: 'left',
    fontFamily: fonts.ui,
  },
  groupTitle: { display: 'block', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 650 },
  groupSub: { display: 'block', color: colors.textFaint, fontSize: fontSize.caption, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  sessionButton: {
    width: '100%',
    minHeight: 38,
    display: 'grid',
    gridTemplateColumns: '18px minmax(0, 1fr) auto',
    alignItems: 'center',
    gap: 8,
    border: 'none',
    background: 'transparent',
    color: colors.text,
    borderRadius: radius.default,
    padding: '5px 6px',
    cursor: 'pointer',
    textAlign: 'left',
    fontFamily: fonts.ui,
  },
  sessionActive: { background: colors.bgCard },
  sessionTitle: { display: 'block', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 600 },
  sessionMeta: { display: 'block', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: colors.textFaint, fontSize: fontSize.caption },
  rowActions: { display: 'inline-flex', alignItems: 'center', gap: 2 },
  inlineInput: {
    width: '100%',
    minWidth: 0,
    background: colors.bg,
    color: colors.text,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.default,
    padding: '2px 6px',
    font: 'inherit',
  },
  primaryButton: {
    width: 32,
    height: 30,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: colors.bgCard,
    color: colors.accent,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.default,
    cursor: 'pointer',
  },
  loadMoreButton: {
    width: '100%',
    height: 30,
    marginTop: spacing.xs,
    background: colors.bgCard,
    color: colors.accent,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.default,
    cursor: 'pointer',
    fontFamily: fonts.ui,
  },
  empty: { color: colors.textMuted, fontSize: fontSize.caption, padding: spacing.md, textAlign: 'center' },
  error: {
    margin: `0 ${spacing.sm}px ${spacing.xs}px`,
    color: colors.warning,
    fontSize: fontSize.caption,
    lineHeight: 1.35,
    wordBreak: 'break-word',
  },
}

function sessionTitle(session: CcChatSessionMeta) {
  return (session.name || '').trim() || session.first_message?.trim() || session.id.slice(-8)
}

function lastPathPart(path: string | null | undefined) {
  if (!path) return ''
  return path.split(/[\\/]/).filter(Boolean).slice(-1)[0] || path
}

function normalizePlanProject(plan: PlanItem | undefined, planId: string | null | undefined) {
  const metaProject = typeof plan?.meta?.project === 'string' ? plan.meta.project : ''
  if (metaProject) return metaProject
  if (plan?.category) return plan.category
  if (planId) return planId.split('/').filter(Boolean)[0] || '未绑定计划'
  return '未绑定计划'
}

function planLabel(plan: PlanItem | undefined, planId: string | null | undefined) {
  if (plan?.topic) return plan.topic
  if (planId) return planId.split('/').filter(Boolean).slice(-1)[0] || planId
  return '未绑定计划'
}

function matchesText(session: CcChatSessionMeta, query: string) {
  if (!query) return true
  const haystack = [
    session.name,
    session.first_message,
    session.last_message,
    session.cwd,
    session.active_plan,
    session.provider,
  ].join('\n').toLowerCase()
  return haystack.includes(query.toLowerCase())
}

export default function ChatStandaloneSidebar({
  sessions,
  selectedId,
  total,
  hasMore,
  search,
  fullText,
  showArchived,
  creating,
  error,
  newProvider,
  newModel,
  providerOptions,
  modelOptions,
  onSearchChange,
  onFullTextChange,
  onShowArchivedChange,
  onProviderChange,
  onModelChange,
  onSelect,
  onCreate,
  onRefresh,
  onLoadMore,
  onRename,
  onArchive,
  onFavorite,
  onCollapse,
}: Props) {
  const [createOpen, setCreateOpen] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('plan')
  const [plans, setPlans] = useState<PlanItem[]>([])
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(['project:未绑定计划']))
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingValue, setEditingValue] = useState('')

  const loadPlans = () => {
    let cancelled = false
    fetch('/api/plans')
      .then((r) => r.ok ? r.json() : { items: [] })
      .then((data) => {
        if (!cancelled) setPlans(Array.isArray(data.items) ? data.items : [])
      })
      .catch(() => {
        if (!cancelled) setPlans([])
      })
    return () => { cancelled = true }
  }

  useEffect(() => {
    return loadPlans()
  }, [])

  const visibleSessions = useMemo(() => {
    return (sessions || [])
      .filter((session) => showArchived || !session.archived)
      .filter((session) => matchesText(session, search))
      .sort((a, b) => Number(b.favorite || false) - Number(a.favorite || false) || b.started_at - a.started_at)
  }, [sessions, search, showArchived])

  const selectedSession = useMemo(() => {
    return (sessions || []).find((session) => session.id === selectedId) || null
  }, [sessions, selectedId])

  const planById = useMemo(() => new Map(plans.map((plan) => [plan.id, plan])), [plans])

  const planGroups = useMemo(() => {
    const grouped = new Map<string, Map<string, CcChatSessionMeta[]>>()
    for (const session of visibleSessions) {
      const plan = planById.get(session.active_plan || '')
      const project = normalizePlanProject(plan, session.active_plan)
      const planName = session.active_plan || '__no_plan__'
      if (!grouped.has(project)) grouped.set(project, new Map())
      const plansForProject = grouped.get(project)!
      if (!plansForProject.has(planName)) plansForProject.set(planName, [])
      plansForProject.get(planName)!.push(session)
    }
    return Array.from(grouped.entries()).map(([project, planMap]) => ({
      project,
      count: Array.from(planMap.values()).reduce((sum, list) => sum + list.length, 0),
      plans: Array.from(planMap.entries()).map(([id, list]) => ({ id, sessions: list })),
    }))
  }, [visibleSessions, planById])

  const folderGroups = useMemo(() => {
    const grouped = new Map<string, CcChatSessionMeta[]>()
    for (const session of visibleSessions) {
      const key = session.cwd || '(no cwd)'
      if (!grouped.has(key)) grouped.set(key, [])
      grouped.get(key)!.push(session)
    }
    return Array.from(grouped.entries()).map(([folderPath, list]) => ({ folderPath, sessions: list }))
  }, [visibleSessions])

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const startRename = (session: CcChatSessionMeta) => {
    setEditingId(session.id)
    setEditingValue((session.name || '').trim() || sessionTitle(session))
  }

  const finishRename = () => {
    if (!editingId) return
    onRename(editingId, editingValue)
    setEditingId(null)
  }

  const createSession = () => {
    setCreateOpen(false)
    onCreate()
  }

  const renderSession = (session: CcChatSessionMeta) => {
    const active = session.id === selectedId
    return (
      <button
        key={session.id}
        type="button"
        style={{ ...S.sessionButton, ...(active ? S.sessionActive : null) }}
        onClick={() => onSelect(session.id)}
        title={`${session.id}\n${session.cwd}${session.active_plan ? `\n${session.active_plan}` : ''}`}
        data-testid={`chat-sidebar-session-${session.id}`}
      >
        <MessageSquare size={14} color={session.alive ? colors.accent : colors.textMuted} />
        <span style={{ minWidth: 0 }}>
          {editingId === session.id ? (
            <input
              style={S.inlineInput}
              value={editingValue}
              autoFocus
              onClick={(event) => event.stopPropagation()}
              onChange={(event) => setEditingValue(event.target.value)}
              onBlur={finishRename}
              onKeyDown={(event) => {
                if (event.key === 'Enter') finishRename()
                if (event.key === 'Escape') setEditingId(null)
              }}
            />
          ) : (
            <>
              <span style={S.sessionTitle}>{sessionTitle(session)}</span>
              <span style={S.sessionMeta}>{(session.provider || 'claude_code').replace('_', '')} · {lastPathPart(session.cwd)} · {session.message_count || 0}</span>
            </>
          )}
        </span>
        <span style={S.rowActions}>
          <span
            role="button"
            tabIndex={0}
            style={{ ...S.iconButton, width: 24, height: 24, color: session.favorite ? colors.accent : colors.textFaint }}
            title={session.favorite ? '取消收藏' : '收藏'}
            onClick={(event) => {
              event.stopPropagation()
              onFavorite(session.id, !session.favorite)
            }}
          >
            <Star size={13} />
          </span>
          <span
            role="button"
            tabIndex={0}
            style={{ ...S.iconButton, width: 24, height: 24 }}
            title="重命名"
            onClick={(event) => {
              event.stopPropagation()
              startRename(session)
            }}
          >
            ...
          </span>
          <span
            role="button"
            tabIndex={0}
            style={{ ...S.iconButton, width: 24, height: 24 }}
            title={session.archived ? '取消归档' : '归档'}
            onClick={(event) => {
              event.stopPropagation()
              onArchive(session.id, !session.archived)
            }}
          >
            <Archive size={13} />
          </span>
        </span>
      </button>
    )
  }

  return (
    <aside
      style={S.root}
      data-testid="chat-standalone-sidebar"
      onKeyDown={(event) => {
        if (event.key === 'Escape' && createOpen) {
          event.preventDefault()
          setCreateOpen(false)
        }
        if (event.key === 'F2' && selectedSession) {
          event.preventDefault()
          startRename(selectedSession)
        }
      }}
    >
      <div style={S.header}>
        <MessageSquare size={18} color={colors.accent} />
        <span style={S.title} data-testid="chat-standalone-brand">OmniChat</span>
        <span style={{ flex: 1 }} />
        <button type="button" style={S.iconButton} onClick={onCollapse} title="收起侧边栏" data-testid="chat-sidebar-collapse">
          <PanelLeftClose size={14} />
        </button>
        <button type="button" style={S.iconButton} onClick={onRefresh} title="刷新">
          <RefreshCw size={14} />
        </button>
        <button
          type="button"
          style={{ ...S.iconButton, ...(createOpen ? S.iconButtonActive : null) }}
          onClick={() => setCreateOpen((value) => !value)}
          disabled={creating}
          title="新建会话"
          data-testid="chat-standalone-new-session"
        >
          <Plus size={14} />
        </button>
      </div>

      {createOpen && (
        <div style={S.createPopover} data-testid="chat-standalone-create-popover">
          <div style={S.createRow}>
            <select
              style={S.select}
              value={newProvider}
              onChange={(event) => onProviderChange(event.target.value as CcChatProvider)}
              title="新会话 Provider"
              data-testid="chat-standalone-provider-select"
            >
              {providerOptions.map((provider) => (
                <option key={provider.value} value={provider.value}>{provider.label}</option>
              ))}
            </select>
            <select
              style={S.select}
              value={newModel}
              onChange={(event) => onModelChange(event.target.value)}
              title="新会话模型"
              data-testid="chat-standalone-model-select"
            >
              {modelOptions.map((model) => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
            <button type="button" style={S.primaryButton} onClick={createSession} disabled={creating} title="创建会话">
              <Plus size={14} />
            </button>
          </div>
        </div>
      )}

      <div style={S.tabs}>
        {([
          ['plan', GitBranch, '计划'],
          ['folder', Folder, '文件夹'],
          ['conversation', List, '对话'],
        ] as const).map(([mode, Icon, label]) => (
          <button
            key={mode}
            type="button"
            style={{ ...S.tab, ...(viewMode === mode ? S.tabActive : null) }}
            onClick={() => setViewMode(mode)}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      <label style={S.searchBox}>
        <Search size={15} color={colors.textMuted} />
        <input
          style={S.searchInput}
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder={viewMode === 'conversation' ? '搜索对话...' : '搜索计划 / 文件夹 / 对话...'}
          data-testid="chat-sidebar-search"
        />
      </label>

      {error && <div style={S.error}>{error}</div>}

      <div style={S.toggles}>
        <label><input type="checkbox" checked={fullText} onChange={(event) => onFullTextChange(event.target.checked)} /> 全文</label>
        <label><input type="checkbox" checked={showArchived} onChange={(event) => onShowArchivedChange(event.target.checked)} /> 归档</label>
        <span style={{ marginLeft: 'auto' }}>{sessions ? `${visibleSessions.length}/${total || visibleSessions.length}` : '...'}</span>
      </div>

      <div style={S.scroll}>
        {viewMode === 'plan' && planGroups.map((projectGroup) => {
          const projectKey = `project:${projectGroup.project}`
          const projectOpen = expanded.has(projectKey)
          return (
            <div key={projectKey} style={S.group}>
              <button type="button" style={S.groupButton} onClick={() => toggle(projectKey)} title={projectGroup.project}>
                {projectOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <GitBranch size={14} color={colors.textMuted} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={S.groupTitle}>{projectGroup.project}</span>
                  <span style={S.groupSub}>{projectGroup.count} sessions</span>
                </span>
              </button>
              {projectOpen && projectGroup.plans.map((planGroup) => {
                const planId = planGroup.id === '__no_plan__' ? null : planGroup.id
                const plan = planById.get(planId || '')
                const planKey = `plan:${projectGroup.project}:${planGroup.id}`
                const planOpen = expanded.has(planKey) || planGroup.sessions.some((session) => session.id === selectedId)
                return (
                  <div key={planKey} style={{ paddingLeft: 16 }}>
                    <button type="button" style={S.groupButton} onClick={() => toggle(planKey)} title={planId || '未绑定计划'}>
                      {planOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <span style={S.groupTitle}>{planLabel(plan, planId)}</span>
                        <span style={S.groupSub}>{planId || 'active_plan = null'} · {planGroup.sessions.length}</span>
                      </span>
                    </button>
                    {planOpen && <div style={{ paddingLeft: 12 }}>{planGroup.sessions.map(renderSession)}</div>}
                  </div>
                )
              })}
            </div>
          )
        })}

        {viewMode === 'folder' && folderGroups.map((group) => {
          const key = `folder:${group.folderPath}`
          const open = expanded.has(key) || group.sessions.some((session) => session.id === selectedId)
          return (
            <div key={key} style={S.group}>
              <button type="button" style={S.groupButton} onClick={() => toggle(key)} title={group.folderPath}>
                {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <Folder size={14} color={colors.textMuted} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={S.groupTitle}>{lastPathPart(group.folderPath)}</span>
                  <span style={S.groupSub}>{group.folderPath} · {group.sessions.length}</span>
                </span>
              </button>
              {open && <div style={{ paddingLeft: 12 }}>{group.sessions.map(renderSession)}</div>}
            </div>
          )
        })}

        {viewMode === 'conversation' && visibleSessions.map(renderSession)}
        {visibleSessions.length === 0 && <div style={S.empty}>没有匹配的会话</div>}
        {hasMore && <button type="button" style={S.loadMoreButton} onClick={onLoadMore}>更多</button>}
      </div>
    </aside>
  )
}
