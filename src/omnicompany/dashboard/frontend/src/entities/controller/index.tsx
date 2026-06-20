import React, { useEffect, useState } from 'react'
import { create } from 'zustand'
import type { Entity } from '../types'
import type { EntityRegistration, EntityResolver } from '../registry'
import HomeThreeCards from './HomeThreeCards'
import ProjectBoard from '../project/ProjectBoard'
import ConversationMaterialCards from './ConversationMaterialCards'
import CcChatPanel from '../cc_session/CcChatPanel'
import { toChatEntity, type CcSessionEntity } from '../cc_session'
import { ccChatApi } from '../../api/ccChatClient'
import { usePanels } from '../../stores/panelsStore'

export interface ControllerEntity extends Entity {
  type: 'controller'
}

const SINGLE: ControllerEntity = {
  type: 'controller',
  id: 'main',
  title: '总控',
  tags: ['fixed', 'boss-sight'],
}

const resolver: EntityResolver<ControllerEntity> = {
  type: 'controller',
  async fetch(id) {
    if (id === 'main') return SINGLE
    throw new Error(`controller: unknown id ${id}`)
  },
  async list() {
    return [SINGLE]
  },
}

/** 2026-06 重做: 总控 = 对话(人↔AI 主交互)。原内置"项目/对话·计划·审阅/总控对话"三选一 toggle
 *  已删 —— 项目板是独立首页(rail「项目」), 不再在总控里重复。保留此 store 仅为兼容旧引用。 */
export type ControllerView = 'project' | 'home' | 'chat'
export const useControllerView = create<{ view: ControllerView; setView: (v: ControllerView) => void }>((set) => ({
  view: 'home',
  setView: (view) => set({ view }),
}))

const S: Record<string, React.CSSProperties> = {
  root: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    minWidth: 0,
    minHeight: 0,
    background: '#0a0a0a',
    color: '#e6edf3',
  },
  bar: {
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    padding: '3px 8px',
    borderBottom: '1px solid #1f2937',
  },
  toggle: { display: 'inline-flex', gap: 0, border: '1px solid #263443', borderRadius: 5, overflow: 'hidden' },
  toggleBtn: {
    border: 0,
    background: 'transparent',
    color: '#9aa7b4',
    padding: '3px 10px',
    cursor: 'pointer',
    fontSize: 14,
  },
  toggleActive: {
    border: 0,
    background: '#10233a',
    color: '#79c0ff',
    padding: '3px 10px',
    cursor: 'pointer',
    fontSize: 14,
    fontWeight: 700,
  },
  matBtn: {
    border: '1px solid #263443',
    background: '#101820',
    color: '#b8c7d9',
    borderRadius: 4,
    padding: '3px 8px',
    cursor: 'pointer',
    fontSize: 14,
  },
  chatWrap: { flex: 1, minHeight: 0, minWidth: 0, display: 'flex' },
  ctxBar: { flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px', borderBottom: '1px solid #161b22', background: '#0b0f14' },
  ctxHint: { color: '#586573', fontSize: 14, textTransform: 'uppercase' as const, marginRight: 2 },
  ctxBtn: { border: '1px solid #263443', background: '#101820', color: '#b8c7d9', borderRadius: 5, padding: '4px 10px', fontSize: 14, cursor: 'pointer' },
  consoleWrap: { flex: 1, minHeight: 0, overflow: 'auto' },
  inner: { maxWidth: 1180, margin: '0 auto', padding: 16 },
  briefingFrame: {
    minHeight: 260,
    border: '1px solid #1f2937',
    borderRadius: 6,
    overflow: 'hidden',
    background: '#0d1117',
  },
  state: { padding: 16, fontSize: 15 },
}

// 用户明示 2026-06-04: 压缩/新会话做成底层 composer 的斜杠命令(进菜单), 不放顶部按钮。
const CONTROLLER_LOCAL_COMMANDS = [
  { name: '/compact', description: '压缩上下文(折叠历史→新会话继续, 减小上下文)', local: true },
  { name: '/new', description: '新会话(归档当前、清除历史)', local: true },
]

/** 解析或新建一个总控(provider=controller)会话, 然后用统一的 CcChatPanel 渲染对话。
 *  复用 cc_session 那套 chat 内核, 不重写。 */
function ControllerChat() {
  const [entity, setEntity] = useState<CcSessionEntity | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<'' | 'new' | 'compact'>('')

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        // 收敛(用户明示 2026-06-03): 只认唯一总控。规则与后端 ControllerWaker._find_active_controllers
        // 一致 —— 未归档(list 已 includeArchived:false 过滤)、活跃、取 started_at 最新的那个,
        // 保证"用户在对话的总控" == "事件唤起的总控", 不再 N 个总控并存各跑各的。
        const list = await ccChatApi.list({ limit: 80, includeArchived: false })
        const controllers = list
          .filter((s) => (s.provider || '') === 'controller')
          .sort((a, b) => (b.started_at || 0) - (a.started_at || 0))
        let meta = controllers.find((s) => s.alive) || controllers[0]
        if (!meta) meta = await ccChatApi.create({ provider: 'controller' })
        if (alive) setEntity(toChatEntity(meta))
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => { alive = false }
  }, [])

  // 新会话(清除历史): 归档当前总控 + 开一个干净的 + 切过去。
  const newSession = async () => {
    if (busy) return
    setBusy('new')
    setError(null)
    try {
      if (entity) { try { await ccChatApi.patchMetadata(entity.id, { archived: true }) } catch { /* 旧会话归档失败不阻断 */ } }
      const meta = await ccChatApi.create({ provider: 'controller' })
      setEntity(toChatEntity(meta))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy('')
    }
  }

  // 压缩上下文: 折叠旧会话历史 → 新开干净总控并以折叠记录起步 → 归档旧会话(后端 /compact)。
  const compact = async () => {
    if (busy || !entity) return
    setBusy('compact')
    setError(null)
    try {
      const meta = await ccChatApi.compact(entity.id)
      setEntity(toChatEntity(meta))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy('')
    }
  }

  // 用户明示 2026-06-04: 压缩/新会话改成底层 composer 的斜杠命令, 不放顶部按钮。
  // 在发送边界拦截这些本地命令(前端动作, 不发给 LLM)。支持中英别名。
  const onSlashCommand = (raw: string): boolean => {
    const cmd = raw.trim().toLowerCase().split(/\s+/)[0]
    if (busy) return true  // 正忙时吞掉, 避免重复触发
    if (cmd === '/compact' || raw.startsWith('/压缩')) { void compact(); return true }
    if (cmd === '/new' || cmd === '/new-session' || cmd === '/newsession' || raw.startsWith('/新会话') || raw.startsWith('/新')) {
      void newSession(); return true
    }
    return false
  }

  // 菜单命令(/compact /new)命中走这里; onSlashCommand 兜底处理中文别名(/压缩 /新会话)。
  const onLocalCommand = (name: string) => { onSlashCommand(name) }

  if (error) return <div style={{ ...S.state, color: '#ff8a80' }}>总控会话连接失败: {error}</div>
  if (!entity) return <div style={{ ...S.state, color: '#8b949e' }}>正在连接总控会话…</div>
  return (
    <CcChatPanel
      key={entity.id}
      entity={entity}
      showContextPanel={false}
      localCommands={CONTROLLER_LOCAL_COMMANDS}
      onLocalCommand={onLocalCommand}
      onSlashCommand={onSlashCommand}
      cleanViewDefault
      cleanViewKey="controller"
      messagesFooter={<ConversationMaterialCards sessionStartedAt={entity.startedAt} activePlan={entity.activePlan} />}
    />
  )
}

const Editor: React.FC<{ entity: ControllerEntity }> = () => {
  const openTab = usePanels((s) => s.openTab)
  const view = useControllerView((s) => s.view)
  const setView = useControllerView((s) => s.setView)
  const tBtn = (on: boolean): React.CSSProperties => ({
    border: 0, background: on ? '#10233a' : 'transparent', color: on ? '#79c0ff' : '#9aa7b4',
    padding: '3px 11px', cursor: 'pointer', fontSize: 14, fontWeight: on ? 700 : 500,
  })
  return (
    <div style={S.root} data-testid="boss-controller-root">
      <div style={S.bar}>
        <div style={{ display: 'inline-flex', border: '1px solid #263443', borderRadius: 5, overflow: 'hidden' }} role="tablist" aria-label="总控视图">
          <button type="button" data-testid="controller-view-home" style={tBtn(view === 'home')} onClick={() => setView('home')}>最近访问</button>
          <button type="button" data-testid="controller-view-project" style={tBtn(view === 'project')} onClick={() => setView('project')}>项目</button>
          <button type="button" data-testid="controller-view-chat" style={tBtn(view === 'chat')} onClick={() => setView('chat')}>总控对话</button>
        </div>
        <button
          type="button"
          data-testid="open-material-registry"
          style={S.matBtn}
          onClick={() => openTab({ type: 'material_registry', id: 'main' }, '任务材料')}
        >
          任务材料
        </button>
      </div>
      {view === 'home' && <div style={{ flex: 1, minHeight: 0 }} data-testid="controller-home"><HomeThreeCards /></div>}
      {view === 'project' && <div style={{ flex: 1, minHeight: 0 }} data-testid="controller-project"><ProjectBoard /></div>}
      {view === 'chat' && <div style={S.chatWrap} data-testid="controller-chat"><ControllerChat /></div>}
    </div>
  )
}

export const controllerRegistration: EntityRegistration<ControllerEntity> = {
  resolver,
  renderer: { type: 'controller', Editor },
  label: '总控',
  icon: '◎',
}
