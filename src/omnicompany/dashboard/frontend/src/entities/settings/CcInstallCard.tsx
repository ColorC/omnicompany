import React, { useEffect, useState } from 'react'
import { ccApi } from '../../api/ccClient'
import { colors, fonts, spacing } from '../../shell/tokens'

type Scope = 'project' | 'user'

interface Status {
  settings_path: string
  installed: boolean
  mcp_command?: string | null
  hook_events?: string[]
}

const S: Record<string, any> = {
  card: { background: colors.bgCard, border: `1px solid ${colors.borderSubtle}`, borderRadius: 4, padding: spacing.lg, marginBottom: spacing.md },
  row: { display: 'flex', gap: spacing.md, marginBottom: spacing.xs, alignItems: 'baseline' as const },
  k: { color: colors.textFaint, minWidth: 110, fontSize: 14 },
  v: { color: colors.textMuted, wordBreak: 'break-all' as const, fontSize: 14 },
  pill: (ok: boolean): React.CSSProperties => ({
    display: 'inline-block', padding: '1px 8px', borderRadius: 3, fontSize: 14,
    color: ok ? '#4caf50' : '#888', background: '#1a1a1a', marginLeft: 8,
  }),
  controls: { display: 'flex', gap: spacing.md, marginTop: spacing.lg, alignItems: 'center', flexWrap: 'wrap' as const },
  btn: (variant: 'primary' | 'danger' | 'ghost'): React.CSSProperties => ({
    padding: '4px 12px', borderRadius: 4, cursor: 'pointer', fontSize: 14, fontFamily: fonts.mono,
    background: variant === 'primary' ? '#1a2a3a' : variant === 'danger' ? '#2a1a1a' : 'transparent',
    color: variant === 'primary' ? colors.accent : variant === 'danger' ? '#ef5350' : colors.textFaint,
    border: `1px solid ${variant === 'primary' ? '#2a3a4a' : variant === 'danger' ? '#4a2a2a' : colors.border}`,
  }),
  scopeSel: {
    background: colors.bgPanel, color: colors.text, border: `1px solid ${colors.border}`,
    padding: '2px 8px', borderRadius: 3, fontSize: 14, fontFamily: fonts.mono,
  },
  cli: { color: colors.textFaint, fontSize: 14, marginTop: spacing.md, fontFamily: fonts.mono },
  cliCmd: { color: '#79c0ff', background: colors.bgPanel, padding: '2px 6px', borderRadius: 3 },
  msg: (ok: boolean): React.CSSProperties => ({ color: ok ? '#4caf50' : '#ef5350', fontSize: 14, marginTop: spacing.sm }),
  hookList: { color: '#9575cd', fontSize: 14, fontFamily: fonts.mono },
}

export default function CcInstallCard() {
  const [scope, setScope] = useState<Scope>('project')
  const [status, setStatus] = useState<Status | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const load = (s: Scope) => {
    setStatus(null)
    ccApi.installStatus(s).then(setStatus).catch((e) => setMsg({ ok: false, text: String(e) }))
  }
  useEffect(() => { load(scope) }, [scope])

  const onInstall = async () => {
    setBusy(true); setMsg(null)
    try {
      const r = await ccApi.install(scope)
      setMsg({ ok: true, text: `已写入 ${r.settings_path}${r.backup ? ` (备份: ${r.backup.split(/[\\/]/).pop()})` : ''}` })
      load(scope)
    } catch (e) {
      setMsg({ ok: false, text: String(e) })
    } finally { setBusy(false) }
  }

  const onUninstall = async () => {
    setBusy(true); setMsg(null)
    try {
      const r = await ccApi.uninstall(scope)
      setMsg({ ok: true, text: r.removed ? `已移除 omnicompany 入口 (备份: ${(r.backup || '').split(/[\\/]/).pop()})` : (r.note || '无变化') })
      load(scope)
    } catch (e) {
      setMsg({ ok: false, text: String(e) })
    } finally { setBusy(false) }
  }

  return (
    <div style={S.card} data-cc-install-card>
      <div style={{ ...S.row, marginBottom: spacing.md }}>
        <span style={{ color: colors.accent, fontSize: 14, fontWeight: 600 }}>Claude Code 集成</span>
        {status && <span style={S.pill(status.installed)} data-cc-install-pill>{status.installed ? '已装' : '未装'}</span>}
      </div>
      <div style={S.row}><span style={S.k}>scope</span>
        <select
          style={S.scopeSel} value={scope} data-cc-scope-select
          onChange={(e) => setScope(e.target.value as Scope)}
        >
          <option value="project">project (&lt;repo&gt;/.claude/settings.json, 推荐)</option>
          <option value="user">user (~/.claude/settings.json, 全局)</option>
        </select>
      </div>
      {status && <>
        <div style={S.row}><span style={S.k}>settings.json</span><span style={S.v}>{status.settings_path}</span></div>
        {status.mcp_command && (
          <div style={S.row}><span style={S.k}>MCP server</span><span style={S.v}>{status.mcp_command} -m omnicompany.dashboard.cc_wrapper.mcp_server</span></div>
        )}
        {status.hook_events && status.hook_events.length > 0 && (
          <div style={S.row}><span style={S.k}>已挂 hook 事件</span><span style={S.hookList}>{status.hook_events.join(' · ')}</span></div>
        )}
      </>}

      <div style={S.controls}>
        <button data-cc-install style={S.btn('primary')} onClick={onInstall} disabled={busy}>
          {status?.installed ? '重装 / 更新' : '安装到 settings.json'}
        </button>
        <button data-cc-uninstall style={S.btn('danger')} onClick={onUninstall} disabled={busy || !status?.installed}>
          移除
        </button>
        <button style={S.btn('ghost')} onClick={() => load(scope)} disabled={busy}>刷新</button>
      </div>

      {msg && <div style={S.msg(msg.ok)}>{msg.text}</div>}

      <div style={S.cli}>
        等价命令行 (CI / 远程 ssh 用): <span style={S.cliCmd}>omni cc install --scope {scope}</span>
        {' '}/ <span style={S.cliCmd}>omni cc status --scope {scope}</span>
        {' '}/ <span style={S.cliCmd}>omni cc uninstall --scope {scope}</span>
        <br/>
        装完后, 在 omnicompany 仓库下用 <span style={S.cliCmd}>claude</span> 启动会话, MCP server + 4 hooks 自动激活.
      </div>
    </div>
  )
}
