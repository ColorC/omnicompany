// plan_audit 实体 — 三点菜单「跑 plan audit」打开的审计报告视图。
// audit 是分钟级 LLM 循环, 后端 POST /api/plan-audit 起后台 job, 这里按 job_id 轮询
// GET /api/plan-audit/{job_id} 直到 done/error, 渲染人读报告(指示清单+状态+证据+未落地汇总)。
import React, { useEffect, useRef, useState } from 'react'
import type { Entity } from '../types'
import type { EntityRegistration } from '../registry'

interface AuditJob {
  status: 'running' | 'done' | 'error'
  against?: string
  target?: string
  elapsed_s?: number
  report_md?: string
  error?: string
  result?: any
}

const S: Record<string, any> = {
  root: { height: '100%', overflow: 'auto', background: '#0a0a0a', color: '#e6edf3', padding: '16px 20px 40px', boxSizing: 'border-box' },
  head: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' },
  title: { fontSize: 17, fontWeight: 700 },
  pill: (tone: string): React.CSSProperties => ({ fontSize: 12, borderRadius: 5, padding: '2px 9px', color: tone, background: '#11181f', border: `1px solid ${tone}44` }),
  meta: { color: '#7d8da0', fontSize: 13 },
  running: { display: 'flex', alignItems: 'center', gap: 10, color: '#9fd0ff', fontSize: 14, padding: '14px 0' },
  spinner: { width: 14, height: 14, border: '2px solid #2b3a49', borderTopColor: '#79c0ff', borderRadius: '50%', display: 'inline-block', animation: 'omni-spin 0.8s linear infinite' },
  report: { whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'var(--mono, ui-monospace, monospace)', fontSize: 13, lineHeight: 1.6, color: '#d7dee7', background: '#0d1117', border: '1px solid #1f2937', borderRadius: 8, padding: '14px 16px' },
  err: { color: '#ff8a80', fontSize: 14, background: '#160d0d', border: '1px solid #5c2626', borderRadius: 8, padding: '12px 14px', whiteSpace: 'pre-wrap' },
}

function PlanAuditView({ entity }: { entity: Entity }) {
  const jobId = entity.id
  const [job, setJob] = useState<AuditJob | null>(null)
  const [pollErr, setPollErr] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    let alive = true
    let netRetries = 0
    const poll = async () => {
      try {
        const r = await fetch(`/api/plan-audit/${encodeURIComponent(jobId)}`)
        if (r.status === 404) {
          // job 不存在/已过期(dashboard 重启会清空进行中的内存 job) → 停止轮询, 别无限 404
          if (alive) setJob({ status: 'error', error: 'audit job 不存在或已过期(dashboard 重启会清空进行中的 job)。请重新发起审计。' })
          return
        }
        if (!r.ok) {
          if (alive && netRetries++ < 5) { setPollErr(`轮询失败: ${r.status}, 重试中…`); timer.current = window.setTimeout(poll, 4000) }
          else if (alive) setJob({ status: 'error', error: `轮询多次失败: ${r.status}` })
          return
        }
        netRetries = 0
        const d = (await r.json()) as AuditJob
        if (!alive) return
        setJob(d); setPollErr(null)
        if (d.status === 'running') timer.current = window.setTimeout(poll, 3000)
      } catch (e: any) {
        if (alive && netRetries++ < 5) { setPollErr(String(e?.message || e)); timer.current = window.setTimeout(poll, 4000) }
        else if (alive) setJob({ status: 'error', error: `轮询失败: ${e?.message || e}` })
      }
    }
    void poll()
    return () => { alive = false; if (timer.current) window.clearTimeout(timer.current) }
  }, [jobId])

  const toneByStatus: Record<string, string> = { running: '#9fd0ff', done: '#3fb950', error: '#ff8a80' }
  const status = job?.status || 'running'

  return (
    <div style={S.root} data-testid="plan-audit-view">
      <style>{'@keyframes omni-spin{to{transform:rotate(360deg)}}'}</style>
      <div style={S.head}>
        <span style={S.title}>落地审计</span>
        <span style={S.pill(toneByStatus[status] || '#9fd0ff')} data-testid="plan-audit-status">{status}</span>
        {job?.against && <span style={S.meta}>{job.against === 'plan' ? 'plan' : '对话'} · {job?.target}</span>}
        {typeof job?.elapsed_s === 'number' && <span style={S.meta}>· {job.elapsed_s}s</span>}
      </div>

      {status === 'running' && (
        <div style={S.running}>
          <span style={S.spinner} />
          审计中… agent 正在读{job?.against === 'plan' ? '相关对话与 plan' : '对话'}、逐条用 grep/read/git 核查落地，分钟级，请稍候。
        </div>
      )}

      {status === 'error' && <div style={S.err} data-testid="plan-audit-error">审计失败: {job?.error || pollErr || '未知错误'}</div>}

      {status === 'done' && (
        <div style={S.report} data-testid="plan-audit-report">{job?.report_md || '(无报告内容)'}</div>
      )}

      {pollErr && status === 'running' && <div style={{ ...S.meta, marginTop: 8 }}>（{pollErr}，重试中…）</div>}
    </div>
  )
}

const auditEntity = (id: string): Entity => ({ type: 'plan_audit', id, title: '审计报告' })

export const planAuditRegistration: EntityRegistration = {
  label: '落地审计',
  icon: 'shield-check',
  resolver: {
    type: 'plan_audit',
    fetch: async (id: string) => auditEntity(id),
    list: async () => [],
  },
  renderer: { type: 'plan_audit', Editor: PlanAuditView as any },
}
