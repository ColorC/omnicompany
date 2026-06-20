/**
 * NotesForTarget — 在任意对象(plan / llm_session / project / material / vilo demo …)旁内联回显
 * "我对它写的草稿/评论", 并可就地用 Composer 新增一条(纯文本 + 拖图)。读写都走中心 authored store,
 * 与草稿箱(entities/authored)同一份数据 —— 满足"重进 plan/session/项目能看到、能就地写"。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { authoredApi, type AuthoredNote, type NoteTarget } from '../../api/authoredClient'
import { usePanels } from '../../stores/panelsStore'
import { colors as C, fontSize as FS, radius as R } from '../../shell/tokens'
import Composer from './Composer'

interface Props {
  kind: string                 // target.kind: 'llm_session' | 'plan' | 'project' | 'material' …
  id: string                   // target 主键(by-target 用)
  target?: NoteTarget          // 写新草稿用的完整 target(默认 {kind,id,title})
  title?: string               // 该对象标题
  uses?: string[]              // 新条目默认用途(默认 ['comment'])
  heading?: string             // 小标题(默认"草稿札记")
}

function usesBadges(u: string[]): string {
  const map: Record<string, string> = { comment: '评论', draft: '草稿', llm_input: 'LLM输入' }
  return (u || []).map((x) => map[x] || x).join(' · ')
}

const btn: React.CSSProperties = {
  background: 'transparent', border: `1px solid ${C.border}`, borderRadius: R.badges,
  cursor: 'pointer', fontSize: FS.small, padding: '3px 10px',
}

export default function NotesForTarget({ kind, id, target, title, uses, heading = '草稿札记' }: Props) {
  const [items, setItems] = useState<AuthoredNote[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [composing, setComposing] = useState(false)
  const openTab = usePanels((s) => s.openTab)

  const reload = useCallback(() => {
    authoredApi.byTarget(kind, id)
      .then((r) => { setItems(r.items); setErr(null) })
      .catch((e) => setErr(String(e)))
  }, [kind, id])

  useEffect(() => { setItems(null); setErr(null); reload() }, [reload])

  const count = items?.length ?? 0

  return (
    <div data-notes-for-target={`${kind}:${id}`} style={{ fontSize: FS.body, color: C.text }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ color: C.textSecondary, fontWeight: 600 }}>{heading}{count ? ` · ${count}` : ''}</span>
        <span style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => setComposing((v) => !v)} style={{ ...btn, color: C.accent }}>
            {composing ? '取消' : '+ 写草稿'}
          </button>
          <button onClick={() => openTab({ type: 'authored', id: 'main' }, '草稿箱')} title="在草稿箱集中管理" style={{ ...btn, color: C.textMuted }}>
            草稿箱 ↗
          </button>
        </span>
      </div>

      {composing && (
        <div style={{ marginBottom: 10 }}>
          <Composer
            target={target || { kind, id, title }}
            uses={uses || ['comment']}
            autoFocus
            placeholder={`对这个${kind === 'plan' ? '计划' : kind === 'llm_session' ? '会话' : kind === 'project' ? '项目' : '对象'}写点什么。纯文本 + 拖图即可。`}
            onSaved={() => { setComposing(false); reload() }}
            onCancel={() => setComposing(false)}
          />
        </div>
      )}

      {err && <div style={{ color: C.warning, fontSize: FS.small, marginBottom: 6 }}>读取/保存出错: {err}</div>}
      {items === null && !err && <div style={{ color: C.textFaint }}>加载中…</div>}
      {items !== null && count === 0 && !composing && (
        <div style={{ color: C.textFaint }}>还没有针对它的草稿/评论。</div>
      )}

      {(items || []).map((n) => (
        <div key={n.id} style={{ borderBottom: `1px solid ${C.borderSubtle}`, padding: '8px 0' }}>
          <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.6 }}>
            {n.content.length > 320 ? n.content.slice(0, 320) + '…' : n.content}
          </div>
          {(n.captures || []).length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
              {n.captures!.map((c) => (
                <img key={c} src={`/api/boss-sight/captures/file?path=${encodeURIComponent(c)}`} alt=""
                  style={{ maxHeight: 84, borderRadius: R.badges, border: `1px solid ${C.border}` }} />
              ))}
            </div>
          )}
          <div style={{ color: C.textFaint, fontSize: FS.small, marginTop: 4, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span>{usesBadges(n.uses)}</span>
            <span>· {n.author}</span>
            {n.project_id && n.project_id !== 'unfiled' && <span>· {n.project_id}</span>}
            {n.created_at && <span>· {n.created_at.slice(0, 16).replace('T', ' ')}</span>}
          </div>
        </div>
      ))}
    </div>
  )
}
