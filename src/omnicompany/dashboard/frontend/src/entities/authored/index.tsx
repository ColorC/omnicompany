import React, { useEffect, useRef, useState } from 'react'
import type { Entity, EntityType } from '../types'
import type { EntityRegistration, EntityResolver } from '../registry'
import { Save, MoreHorizontal, Trash2, Copy, FolderInput, ArrowUpRight, ArrowLeft } from 'lucide-react'
import { usePanels } from '../../stores/panelsStore'
import { authoredApi, type AuthoredNote } from '../../api/authoredClient'
import { colors as TC, fontSize as TFS, radius as TR } from '../../shell/tokens'
import { relTimeZh } from '../../lib/time'
import Composer from './Composer'

// 统一札记(评论·草稿·决策)集中管理面。一个 tab 看全部自撰内容: 列表+筛选+搜索+跳转+编辑+删除。
export interface AuthoredEntity extends Entity {
  type: 'authored'
}

const SINGLE: AuthoredEntity = {
  type: 'authored',
  id: 'main',
  title: '札记',
  tags: ['boss-sight', 'authored'],
}

const resolver: EntityResolver<AuthoredEntity> = {
  type: 'authored',
  async fetch(id) {
    if (id === 'main') return SINGLE
    return { ...SINGLE, id }
  },
  async list() { return [SINGLE] },
}

const TARGET_KIND_LABEL: Record<string, string> = {
  material: '审阅材料', project: '项目', plan: '计划',
  llm_session: '对话', page_element: '页面元素', new_object: '新建对象',
}
const USES_LABEL: Record<string, string> = { comment: '评论', draft: '草稿', llm_input: 'LLM输入' }
const STATUS_LABEL: Record<string, string> = {
  saved: '已保存', delivered: '已发送', read: '已读', to_todo: '待办', todo_done: '已办',
}

function targetSummary(t: AuthoredNote['target']): string {
  if (!t || !t.kind) return '(无关联)'
  const k = TARGET_KIND_LABEL[t.kind] || t.kind
  const sub = t.sub_kind ? ` · ${t.sub_kind}${t.sub_id ? ':' + t.sub_id : ''}` : ''
  const id = t.id ? ` ${String(t.id).slice(0, 28)}` : ''
  return `${k}${id}${sub}`
}

function jumpRefFor(t: AuthoredNote['target']): { type: EntityType; id: string } | { url: string } | null {
  if (!t || !t.kind) return null
  if (t.kind === 'material' && t.id) return { type: 'review_material', id: String(t.id) }
  if (t.kind === 'plan' && t.id) return { type: 'plan', id: String(t.id) }
  if (t.kind === 'project' && t.id) return { type: 'project', id: String(t.id) }
  if (t.kind === 'llm_session' && t.id) return { type: 'cc_session', id: String(t.id) }
  if (t.url) return { url: String(t.url) }
  return null
}

const Panel: React.FC<{ entity: AuthoredEntity }> = () => {
  const openTab = usePanels((s) => s.openTab)
  const [items, setItems] = useState<AuthoredNote[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [fKind, setFKind] = useState('')
  const [fProject, setFProject] = useState('')
  const [fUses, setFUses] = useState('')
  const [q, setQ] = useState('')
  const [draft, setDraft] = useState('')
  const [status, setStatus] = useState('')
  const [title, setTitle] = useState('')
  const [composing, setComposing] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)

  // 窄容器自适应: 挂进 vscode 原生侧栏(~300px)时左 340 列表 + 右编辑列并排放不下,
  // 右编辑列被压成≈0 → "点新建/点条目看不见在编辑". 窄态切单列抽屉式(列表 ↔ 编辑切换).
  const rootRef = useRef<HTMLDivElement>(null)
  const [narrow, setNarrow] = useState(false)
  useEffect(() => {
    const el = rootRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setNarrow(e.contentRect.width < 560)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const load = () => {
    setLoading(true)
    authoredApi.list({ target: fKind || undefined, project: fProject || undefined, uses: fUses || undefined, q: q || undefined })
      .then((r) => {
        setItems(r.items || [])
        setSelectedId((prev) => (prev && r.items.some((n) => n.id === prev)) ? prev : (r.items[0]?.id || null))
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [fKind, fProject, fUses, q]) // eslint-disable-line react-hooks/exhaustive-deps

  const selected = items.find((n) => n.id === selectedId) || null
  useEffect(() => { setDraft(selected?.content || ''); setStatus(selected?.feedback_status || ''); setTitle(selected?.title || '') }, [selectedId]) // eslint-disable-line react-hooks/exhaustive-deps

  const projects = Array.from(new Set(items.map((n) => n.project_id).filter(Boolean)))
  const showEditor = composing || !!selected  // 窄态: 决定显示列表还是编辑抽屉

  const onJump = (n: AuthoredNote) => {
    const ref = jumpRefFor(n.target)
    if (!ref) return
    if ('url' in ref) { window.location.href = ref.url; return }
    openTab(ref, targetSummary(n.target))
  }
  const onSave = () => {
    if (!selected) return
    authoredApi.update(selected.id, { content: draft, feedback_status: status || undefined, title }).then(load)
  }
  const onDelete = () => {
    if (!selected || !window.confirm('删除这条札记？(软归档)')) return
    authoredApi.remove(selected.id).then(load)
  }
  const onCopyPath = () => { if (selected?.json_path) navigator.clipboard?.writeText(selected.json_path) }
  const onExportDraft = async () => {
    if (!selected) return
    const t: any = selected.target || {}
    const fromTarget = (t.new_object && t.new_object.dest_dir) || t.dest_dir || ''
    const dest = window.prompt('导出草稿成品到哪个项目目录?(绝对路径, 或相对 workspace)', fromTarget)
    if (!dest) return
    try {
      const r = await authoredApi.exportDraft(selected.id, { dest_dir: dest })
      window.alert('已导出成品到:\n' + r.exported_path); load()
    } catch (e) {
      if (String(e).includes('409') && window.confirm('文件已存在, 覆盖?')) {
        try {
          const r = await authoredApi.exportDraft(selected.id, { dest_dir: dest, overwrite: true })
          window.alert('已覆盖导出:\n' + r.exported_path); load()
        } catch (e2) { window.alert('导出失败: ' + e2) }
      } else { window.alert('导出失败: ' + e) }
    }
  }

  const sel: React.CSSProperties = { flex: 1, minWidth: 0, background: TC.bgCard, color: TC.text, border: `1px solid ${TC.border}`, borderRadius: TR.badges, padding: '6px 8px', fontSize: TFS.small }
  const ghost: React.CSSProperties = { background: 'transparent', color: TC.textSecondary, border: `1px solid ${TC.border}`, borderRadius: TR.default, padding: '6px 12px', fontSize: TFS.body, cursor: 'pointer' }
  const primary: React.CSSProperties = { background: TC.accent, color: '#fff', border: 'none', borderRadius: TR.default, padding: '7px 16px', fontSize: TFS.body, fontWeight: 600, cursor: 'pointer' }
  const menuItem: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left', background: 'transparent', color: TC.text, border: 'none', borderRadius: TR.badges, padding: '8px 10px', fontSize: TFS.body, cursor: 'pointer' }

  return (
    <div ref={rootRef} style={{ display: 'flex', flexDirection: narrow ? 'column' : 'row', height: '100%', fontSize: TFS.body, background: TC.bg, color: TC.text }}>
      {/* 左: 新建 + 筛选 + 列表 (窄态占满宽; 进编辑/新建抽屉时隐藏) */}
      <div style={{
        width: narrow ? '100%' : 340,
        minWidth: narrow ? 0 : 280,
        ...(narrow ? { borderBottom: `1px solid ${TC.border}` } : { borderRight: `1px solid ${TC.border}` }),
        display: narrow && showEditor ? 'none' : 'flex',
        flex: narrow ? 1 : undefined,
        minHeight: 0,
        flexDirection: 'column',
        background: TC.bgPanel,
      }}>
        <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8, borderBottom: `1px solid ${TC.border}` }}>
          <button type="button" data-testid="authored-new" onClick={() => { setComposing(true); setSelectedId(null) }} style={{ ...primary, padding: '9px 12px' }}>＋ 新建草稿</button>
          <input placeholder="搜索内容 / 对象 / 项目…" value={q} onChange={(e) => setQ(e.target.value)}
                 style={{ padding: '7px 10px', borderRadius: TR.default, border: `1px solid ${TC.border}`, background: TC.bgCard, color: TC.text, fontSize: TFS.body, outline: 'none' }} />
          <div style={{ display: 'flex', gap: 6 }}>
            <select value={fKind} onChange={(e) => setFKind(e.target.value)} style={sel}>
              <option value="">全部对象</option>
              {Object.entries(TARGET_KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select value={fProject} onChange={(e) => setFProject(e.target.value)} style={sel}>
              <option value="">全部项目</option>
              {projects.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <select value={fUses} onChange={(e) => setFUses(e.target.value)} style={sel}>
              <option value="">全部用途</option>
              {Object.entries(USES_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div style={{ color: TC.textMuted, fontSize: TFS.small }}>{loading ? '加载中…' : `${items.length} 条`}</div>
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          {items.map((n) => {
            const active = n.id === selectedId && !composing
            return (
              <button key={n.id} onClick={() => { setComposing(false); setSelectedId(n.id) }}
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '10px 14px', border: 'none',
                         borderLeft: `2px solid ${active ? TC.accent : 'transparent'}`,
                         borderBottom: `1px solid ${TC.borderSubtle}`, cursor: 'pointer',
                         background: active ? TC.bgCard : 'transparent', color: TC.text }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <div style={{ flex: 1, fontWeight: 600, fontSize: TFS.body, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {n.title?.trim() || n.content.slice(0, 46) || '(空)'}
                  </div>
                  {relTimeZh(n.updated_at || n.created_at) && (
                    <span style={{ flexShrink: 0, color: TC.textFaint, fontSize: TFS.small }}>{relTimeZh(n.updated_at || n.created_at)}</span>
                  )}
                </div>
                <div style={{ color: TC.textMuted, fontSize: TFS.small, marginTop: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {targetSummary(n.target)} · {STATUS_LABEL[n.feedback_status] || n.feedback_status}
                </div>
              </button>
            )
          })}
          {!items.length && !loading && <div style={{ padding: 18, color: TC.textFaint }}>没有匹配的草稿。</div>}
        </div>
      </div>

      {/* 右: 新建 / 文档式编辑(占满宽高); 窄态作抽屉, 仅编辑/新建时显示, 顶部加返回 */}
      <div style={{ flex: 1, minWidth: 0, display: narrow && !showEditor ? 'none' : 'flex', flexDirection: 'column', overflow: 'hidden', background: TC.bg }}>
        {narrow && showEditor && (
          <button type="button" data-testid="authored-narrow-back"
            onClick={() => { setComposing(false); setSelectedId(null) }}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', border: 'none', borderBottom: `1px solid ${TC.border}`, background: TC.bgPanel, color: TC.accent, cursor: 'pointer', fontSize: TFS.body, textAlign: 'left', flexShrink: 0 }}>
            <ArrowLeft size={15} /> 返回列表
          </button>
        )}
        {composing ? (
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: '18px 28px 22px' }}>
            <div style={{ fontWeight: 700, marginBottom: 14, fontSize: TFS.heading }}>新建草稿</div>
            <Composer
              uses={['draft']}
              fill
              autoFocus
              placeholder="随手写。纯文本 + 拖图即可,格式化和正式化交给 AI。可不挂对象(自由草稿)。"
              onSaved={() => { setComposing(false); load() }}
              onCancel={() => setComposing(false)}
            />
          </div>
        ) : !selected ? (
          <div style={{ color: TC.textFaint, fontSize: TFS.title, margin: 'auto' }}>
            选一条草稿查看 / 编辑,或点左上「＋ 新建草稿」。
          </div>
        ) : (
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12, padding: '16px 28px 18px' }}>
              {/* 上下文(针对谁) */}
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', color: TC.textMuted, fontSize: TFS.small }}>
                <span>针对 <span style={{ color: TC.textSecondary }}>{targetSummary(selected.target)}</span></span>
                {jumpRefFor(selected.target) && (
                  <button onClick={() => onJump(selected)} title="跳到该对象"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: 'transparent', color: TC.link, border: 'none', cursor: 'pointer', fontSize: TFS.small }}>
                    <ArrowUpRight size={14} /> 跳转
                  </button>
                )}
                {selected.project_id && selected.project_id !== 'unfiled' && <span>· 项目 {selected.project_id}</span>}
                {(selected.uses || []).map((u) => <span key={u} style={{ background: TC.bgCard, border: `1px solid ${TC.border}`, padding: '2px 8px', borderRadius: TR.badges, color: TC.textSecondary }}>{USES_LABEL[u] || u}</span>)}
              </div>

              {/* 标题(可重命名): 列表与页签按它显示; 留空回退正文首行。改完点「保存」生效。 */}
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'Enter')) { e.preventDefault(); onSave() } }}
                placeholder={(selected.content.slice(0, 46) || '给这条起个名字') + '（标题可选，留空用正文首行）'}
                data-testid="authored-title-input"
                style={{ width: '100%', boxSizing: 'border-box', background: TC.bgDoc, color: TC.text, border: `1px solid ${TC.border}`, borderRadius: TR.default, padding: '8px 12px', fontSize: TFS.title, fontWeight: 600, outline: 'none' }}
              />

              {/* 编辑器: 顶部工具栏 + 干净正文(占满剩余高度) */}
              <div style={{ flex: 1, minHeight: 0, border: `1px solid ${TC.border}`, borderRadius: TR.default, background: TC.bgDoc, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 6px', borderBottom: `1px solid ${TC.borderSubtle}` }}>
                  <div style={{ flex: 1 }} />
                  <select value={status} onChange={(e) => setStatus(e.target.value)} title="反馈状态"
                    style={{ background: TC.bgCard, color: TC.text, border: `1px solid ${TC.border}`, borderRadius: TR.badges, padding: '4px 6px', fontSize: TFS.small, height: 30 }}>
                    {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <button onClick={onSave} title="保存(Ctrl/⌘+S)"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 30, padding: '0 14px', background: TC.accent, color: '#fff', border: 'none', borderRadius: TR.badges, fontSize: TFS.body, fontWeight: 600, cursor: 'pointer' }}>
                    <Save size={15} /> 保存
                  </button>
                  <div style={{ position: 'relative' }}>
                    <button onClick={() => setMoreOpen((v) => !v)} title="更多"
                      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', height: 30, width: 32, background: 'transparent', color: TC.textMuted, border: 'none', borderRadius: TR.badges, cursor: 'pointer' }}>
                      <MoreHorizontal size={18} />
                    </button>
                    {moreOpen && (
                      <>
                        <div style={{ position: 'fixed', inset: 0, zIndex: 39 }} onClick={() => setMoreOpen(false)} />
                        <div style={{ position: 'absolute', top: 34, right: 0, zIndex: 40, minWidth: 184, background: TC.bgCard, border: `1px solid ${TC.border}`, borderRadius: TR.default, boxShadow: '0 10px 30px rgba(0,0,0,.5)', padding: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
                          {(selected.uses || []).includes('draft') && (
                            <button onClick={() => { setMoreOpen(false); void onExportDraft() }} style={menuItem}><FolderInput size={15} /> 导出成品到目录</button>
                          )}
                          <button onClick={() => { setMoreOpen(false); onCopyPath() }} style={menuItem}><Copy size={15} /> 复制文件位置</button>
                          <button onClick={() => { setMoreOpen(false); onDelete() }} style={{ ...menuItem, color: TC.warning }}><Trash2 size={15} /> 删除</button>
                        </div>
                      </>
                    )}
                  </div>
                </div>
                <textarea value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false}
                  onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'Enter')) { e.preventDefault(); onSave() } }}
                  style={{ flex: 1, minHeight: 0, width: '100%', boxSizing: 'border-box', padding: '16px 18px', border: 'none', background: 'transparent', color: TC.text, fontFamily: 'inherit', fontSize: TFS.doc, lineHeight: 1.6, resize: 'none', outline: 'none' }} />
                {(selected.captures || []).length > 0 && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', padding: '0 16px 14px' }}>
                    {selected.captures!.map((c) => (
                      <img key={c} src={`/api/boss-sight/captures/file?path=${encodeURIComponent(c)}`} alt="" style={{ maxHeight: 140, borderRadius: TR.badges, border: `1px solid ${TC.border}` }} />
                    ))}
                  </div>
                )}
              </div>
              {(selected.extra as any)?.exported_to && (
                <div style={{ color: TC.success, fontSize: TFS.small }}>已导出成品 → {(selected.extra as any).exported_to}</div>
              )}
              <div style={{ color: TC.textFaint, fontSize: TFS.small }}>作者 {selected.author} · 创建 {selected.created_at?.slice(0, 19).replace('T', ' ')}</div>
            </div>
          )}
      </div>
    </div>
  )
}

export const authoredRegistration: EntityRegistration<AuthoredEntity> = {
  resolver,
  renderer: { type: 'authored', Editor: Panel },
  label: '札记',
  icon: '✎',
}
