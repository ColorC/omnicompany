/**
 * NewPlanPanel — 项目内"一键新建计划书"。用户写主题 + 纯文本草稿, 勾"AI 正式化"则交性价比模型
 * 整理成规范计划书, 落成该项目计划目录的 plan.md, 并打开它。后端 POST /api/plans。
 */
import React, { useState } from 'react'
import { createPlan } from '../../api/projectsClient'
import { usePanels } from '../../stores/panelsStore'
import { colors as C, fontSize as FS, radius as R } from '../../shell/tokens'

interface Props {
  projectId: string
  onCreated?: (planId: string) => void
  onCancel?: () => void
}

export default function NewPlanPanel({ projectId, onCreated, onCancel }: Props) {
  const [topic, setTopic] = useState('')
  const [content, setContent] = useState('')
  const [formalize, setFormalize] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const openTab = usePanels((s) => s.openTab)

  const create = async () => {
    if (!topic.trim() || busy) return
    setBusy(true); setErr(null)
    try {
      const res = await createPlan({
        topic: topic.trim(), project_id: projectId,
        content: content.trim(), formalize,
      })
      openTab({ type: 'plan', id: res.plan_id }, topic.trim() || (res.plan_id.split('/').pop() || '计划'))
      onCreated?.(res.plan_id)
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ border: `1px solid ${C.border}`, borderRadius: R.default, background: C.bgDoc, padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }} data-testid="new-plan-panel">
      <input
        autoFocus
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
        placeholder="计划书标题 / 主题(例:vilo 卡牌平衡性调整)"
        style={{ width: '100%', boxSizing: 'border-box', background: 'transparent', color: C.text, border: 'none', outline: 'none', fontSize: FS.title, fontWeight: 700, padding: '2px 0' }}
      />
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); void create() } }}
        placeholder={'随手写要点、背景、想法 —— 纯文本就行。勾上「AI 正式化」我会整理成规范计划书。(Ctrl/⌘+Enter 创建)'}
        spellCheck={false}
        style={{ width: '100%', boxSizing: 'border-box', minHeight: 160, resize: 'vertical', background: 'transparent', color: C.text, border: 'none', outline: 'none', fontSize: FS.doc, lineHeight: 1.6, fontFamily: 'inherit' }}
      />
      {err && <div style={{ color: C.warning, fontSize: FS.small }}>创建失败: {err}</div>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button
          type="button" onClick={() => void create()} disabled={busy || !topic.trim()}
          style={{ background: C.accent, color: '#fff', border: 'none', borderRadius: R.default, padding: '8px 18px', fontSize: FS.body, fontWeight: 600, cursor: busy ? 'default' : 'pointer', opacity: (busy || !topic.trim()) ? 0.5 : 1 }}
        >{busy ? (formalize ? 'AI 正在整理成计划书…' : '创建中…') : '创建计划书'}</button>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: C.textSecondary, fontSize: FS.body, cursor: 'pointer' }}>
          <input type="checkbox" checked={formalize} onChange={(e) => setFormalize(e.target.checked)} />
          AI 正式化(把纯文本整理成规范计划书)
        </label>
        {onCancel && (
          <button type="button" onClick={onCancel}
            style={{ marginLeft: 'auto', background: 'transparent', color: C.textMuted, border: `1px solid ${C.border}`, borderRadius: R.default, padding: '7px 14px', fontSize: FS.body, cursor: 'pointer' }}
          >取消</button>
        )}
      </div>
    </div>
  )
}
