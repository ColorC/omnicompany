import React, { useEffect, useMemo, useState } from 'react'
import {
  bossSightApi,
  type BossSightControlItem,
  type BossSightControlResponse,
  type BossSightObservabilityDimension,
  type BossSightObservabilitySettings,
  type BossSightObservationEvent,
  type BossSightUserPrefs,
} from '../../api/bossSightClient'

const CONTROL_ORDER = [
  'controller.auto_wake',
  'reviewstage.push_to_user',
  'spawn.hard_block',
  'observability.enabled',
]

const CONTROL_COPY: Record<string, { title: string; body: string }> = {
  'controller.auto_wake': { title: '总控自动唤起', body: '评论、阻断、完成事件可以唤起 controller。' },
  'reviewstage.push_to_user': { title: '审阅推送', body: '重要审阅材料可以推到用户视野。' },
  'spawn.hard_block': { title: '硬阻断', body: '高风险 subagent 动作继续走硬阻断。' },
  'observability.enabled': { title: '观测总开关', body: '允许记录界面行为给 controller 读取。' },
}

const DIMENSIONS: BossSightObservabilityDimension[] = ['click', 'selection', 'toggle_change', 'view_dwell']

const DIM_COPY: Record<BossSightObservabilityDimension, { title: string; body: string }> = {
  click: { title: '点击', body: '记录用户点击过的界面目标。' },
  selection: { title: '圈选', body: '记录用户选中的文字或元素线索。' },
  toggle_change: { title: '开关变更', body: '记录设置和开关变化。' },
  view_dwell: { title: '视图停留', body: '记录用户停留在哪个视图。' },
}

const S: Record<string, React.CSSProperties> = {
  card: {
    background: '#0a0f14',
    border: '1px solid #263443',
    borderRadius: 6,
    padding: 14,
    marginBottom: 10,
    color: '#dce5ee',
  },
  header: { display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', marginBottom: 12 },
  title: { color: '#9fd0ff', fontSize: 15, fontWeight: 700 },
  subtitle: { color: '#8a98a7', marginTop: 4, lineHeight: 1.5 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 },
  item: { border: '1px solid #1f2b37', borderRadius: 6, padding: 10, background: '#0f1720' },
  itemTop: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  itemTitle: { fontSize: 15, fontWeight: 700, color: '#eef5fb' },
  itemBody: { color: '#8392a1', lineHeight: 1.5, marginTop: 5 },
  sectionTitle: { color: '#9fd0ff', fontSize: 14, textTransform: 'uppercase', margin: '14px 0 8px' },
  switch: { width: 18, height: 18, accentColor: '#58a6ff', flexShrink: 0 },
  form: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8, alignItems: 'end' },
  inputWrap: { display: 'grid', gap: 4 },
  label: { color: '#7b8b9a', fontSize: 14 },
  input: { background: '#05080c', border: '1px solid #253341', borderRadius: 4, color: '#dce5ee', padding: '7px 8px', minWidth: 0 },
  button: { background: '#1f6feb', border: '1px solid #2f81f7', borderRadius: 4, color: '#fff', padding: '7px 10px', cursor: 'pointer' },
  ghostButton: { background: '#101820', border: '1px solid #2b3a49', borderRadius: 4, color: '#b7c8d9', padding: '6px 9px', cursor: 'pointer' },
  muted: { color: '#778899' },
  rows: { display: 'grid', gap: 6 },
  row: { display: 'flex', justifyContent: 'space-between', gap: 10, border: '1px solid #1d2731', borderRadius: 4, padding: '7px 8px', color: '#aebdcc' },
  badge: { color: '#7ee787', fontSize: 14 },
  error: { color: '#ff7b72' },
}

function updateControl(prev: BossSightControlResponse | null, item: BossSightControlItem): BossSightControlResponse | null {
  if (!prev) return prev
  return {
    ...prev,
    items: prev.items.map((existing) => existing.key === item.key ? item : existing),
    by_key: { ...prev.by_key, [item.key]: item },
  }
}

function safeTime(value?: string) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

function formatEvent(event: BossSightObservationEvent) {
  const target = event.target ? ` · ${event.target}` : ''
  return `${event.dimension}${target}`
}

export default function BossSightControlCard() {
  const [controls, setControls] = useState<BossSightControlResponse | null>(null)
  const [settings, setSettings] = useState<BossSightObservabilitySettings | null>(null)
  const [prefs, setPrefs] = useState<BossSightUserPrefs | null>(null)
  const [recent, setRecent] = useState<BossSightObservationEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [allowForm, setAllowForm] = useState({ scope: 'user', tool: '', pattern: '', reason: '' })

  useEffect(() => {
    let alive = true
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [controlRes, settingsRes, prefsRes, recentRes] = await Promise.all([
          bossSightApi.getControl(),
          bossSightApi.getObservabilitySettings(),
          bossSightApi.getUserPrefs(),
          bossSightApi.recentObservations(8),
        ])
        if (!alive) return
        setControls(controlRes)
        setSettings(settingsRes)
        setPrefs(prefsRes)
        setRecent(recentRes.items)
      } catch (e) {
        if (alive) setError(String(e))
      } finally {
        if (alive) setLoading(false)
      }
    }
    load()
    return () => { alive = false }
  }, [])

  const controlItems = useMemo(() => {
    if (!controls) return []
    return CONTROL_ORDER.map((key) => controls.by_key[key]).filter(Boolean)
  }, [controls])

  async function recordSettingEvent(target: string, value: unknown) {
    try {
      await bossSightApi.recordObservation({
        dimension: 'toggle_change',
        surface: 'settings',
        target,
        value,
        meta: { source: 'BossSightControlCard' },
      })
    } catch {
      // Observation must not block settings changes.
    }
  }

  async function toggleControl(item: BossSightControlItem) {
    const next = !item.value
    setBusyKey(item.key)
    setMessage(null)
    try {
      const updated = await bossSightApi.setControl(item.key, next, 'human', 'settings panel toggle')
      setControls((prev) => updateControl(prev, updated))
      await recordSettingEvent(`control:${item.key}`, next)
    } catch (e) {
      setMessage(String(e))
    } finally {
      setBusyKey(null)
    }
  }

  async function toggleDimension(dimension: BossSightObservabilityDimension) {
    if (!settings) return
    const next = !settings.dimensions[dimension]
    setBusyKey(`obs:${dimension}`)
    setMessage(null)
    try {
      const updated = await bossSightApi.setObservabilitySettings(
        { [dimension]: next },
        'human',
        'settings panel toggle',
      )
      setSettings(updated)
      await recordSettingEvent(`observability:${dimension}`, next)
    } catch (e) {
      setMessage(String(e))
    } finally {
      setBusyKey(null)
    }
  }

  async function submitPermanentAllow(e: React.FormEvent) {
    e.preventDefault()
    if (!allowForm.tool.trim()) {
      setMessage('tool 必填')
      return
    }
    setBusyKey('permanent_allow')
    setMessage(null)
    try {
      const entry = await bossSightApi.addPermanentAllow({
        scope: allowForm.scope,
        tool: allowForm.tool,
        pattern: allowForm.pattern,
        reason: allowForm.reason,
      })
      setPrefs((prev) => ({
        ...(prev || { version: 1, permanent_allow: [] }),
        permanent_allow: [...(prev?.permanent_allow || []), entry],
      }))
      setAllowForm({ scope: 'user', tool: '', pattern: '', reason: '' })
      setMessage('已写入 user_prefs.json')
      await recordSettingEvent('user_prefs:permanent_allow', { tool: entry.tool, scope: entry.scope })
    } catch (err) {
      setMessage(String(err))
    } finally {
      setBusyKey(null)
    }
  }

  return (
    <div style={S.card} data-testid="boss-sight-control-card">
      <div style={S.header}>
        <div>
          <div style={S.title}>BOSS SIGHT 双控与观测</div>
          <div style={S.subtitle}>这里的永久允许只进入用户偏好，不写入项目 guard。</div>
        </div>
        <button
          type="button"
          style={S.ghostButton}
          onClick={() => bossSightApi.recentObservations(8).then((r) => setRecent(r.items)).catch((e) => setMessage(String(e)))}
        >
          刷新
        </button>
      </div>

      {loading && <div style={S.muted}>加载中...</div>}
      {error && <div style={S.error}>{error}</div>}

      {!loading && !error && (
        <>
          <div style={S.sectionTitle}>双控开关</div>
          <div style={S.grid}>
            {controlItems.map((item) => {
              const copy = CONTROL_COPY[item.key] || { title: item.label || item.key, body: item.description || '' }
              return (
                <label key={item.key} style={S.item} data-testid={`control-${item.key}`}>
                  <span style={S.itemTop}>
                    <span>
                      <span style={S.itemTitle}>{copy.title}</span>
                      <span style={{ ...S.badge, marginLeft: 8 }}>{item.value ? '开启' : '关闭'}</span>
                    </span>
                    <input
                      aria-label={copy.title}
                      type="checkbox"
                      checked={item.value}
                      disabled={busyKey === item.key}
                      style={S.switch}
                      onChange={() => toggleControl(item)}
                    />
                  </span>
                  <span style={S.itemBody}>{copy.body}</span>
                  <span style={{ ...S.muted, display: 'block', marginTop: 6 }}>
                    {item.updated_by} · {safeTime(item.updated_at)}
                  </span>
                </label>
              )
            })}
          </div>

          <div style={S.sectionTitle}>观测维度</div>
          <div style={S.grid}>
            {DIMENSIONS.map((dimension) => {
              const copy = DIM_COPY[dimension]
              const checked = settings?.dimensions[dimension] ?? true
              return (
                <label key={dimension} style={S.item} data-testid={`observability-${dimension}`}>
                  <span style={S.itemTop}>
                    <span>
                      <span style={S.itemTitle}>{copy.title}</span>
                      <span style={{ ...S.badge, marginLeft: 8 }}>{checked ? '记录' : '关闭'}</span>
                    </span>
                    <input
                      aria-label={copy.title}
                      type="checkbox"
                      checked={checked}
                      disabled={busyKey === `obs:${dimension}`}
                      style={S.switch}
                      onChange={() => toggleDimension(dimension)}
                    />
                  </span>
                  <span style={S.itemBody}>{copy.body}</span>
                </label>
              )
            })}
          </div>

          <div style={S.sectionTitle}>永久允许偏好</div>
          <form style={S.form} onSubmit={submitPermanentAllow} data-testid="permanent-allow-form">
            <label style={S.inputWrap}>
              <span style={S.label}>scope</span>
              <input
                style={S.input}
                value={allowForm.scope}
                onChange={(e) => setAllowForm((f) => ({ ...f, scope: e.target.value }))}
              />
            </label>
            <label style={S.inputWrap}>
              <span style={S.label}>tool</span>
              <input
                style={S.input}
                value={allowForm.tool}
                onChange={(e) => setAllowForm((f) => ({ ...f, tool: e.target.value }))}
              />
            </label>
            <label style={S.inputWrap}>
              <span style={S.label}>pattern</span>
              <input
                style={S.input}
                value={allowForm.pattern}
                onChange={(e) => setAllowForm((f) => ({ ...f, pattern: e.target.value }))}
              />
            </label>
            <label style={S.inputWrap}>
              <span style={S.label}>reason</span>
              <input
                style={S.input}
                value={allowForm.reason}
                onChange={(e) => setAllowForm((f) => ({ ...f, reason: e.target.value }))}
              />
            </label>
            <button type="submit" style={S.button} disabled={busyKey === 'permanent_allow'}>
              写入偏好
            </button>
          </form>
          {message && <div style={{ ...(message.includes('Error') ? S.error : S.muted), marginTop: 8 }}>{message}</div>}

          <div style={S.sectionTitle}>最近观测</div>
          <div style={S.rows} data-testid="recent-observations">
            {recent.length === 0 && <div style={S.muted}>暂无观测事件</div>}
            {recent.map((event) => (
              <div key={event.id} style={S.row}>
                <span>{formatEvent(event)}</span>
                <span style={S.muted}>{safeTime(event.recorded_at)}</span>
              </div>
            ))}
          </div>

          <div style={S.sectionTitle}>已记录永久允许</div>
          <div style={S.rows} data-testid="permanent-allow-list">
            {(prefs?.permanent_allow || []).length === 0 && <div style={S.muted}>暂无永久允许偏好</div>}
            {(prefs?.permanent_allow || []).slice(-4).reverse().map((entry) => (
              <div key={entry.id} style={S.row}>
                <span>{entry.tool}{entry.pattern ? ` · ${entry.pattern}` : ''}</span>
                <span style={S.muted}>{entry.scope}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
