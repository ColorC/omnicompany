/**
 * ClaudeCodeSession Editor — xterm.js terminal bridged to backend PTY via WebSocket.
 *
 * Protocol (matches src/omnicompany/dashboard/cc_wrapper/api.py):
 *   client → server: {type:"input",  data:string} | {type:"resize", cols, rows}
 *   server → client: {type:"snapshot", chunks:string[]} | {type:"output", data} | {type:"exit", reason}
 *
 * Architecture is a clean-room reimpl of the public PTY-over-WS pattern; xterm.js
 * itself is MIT (no AGPL contagion).
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import type { CcSessionEntity } from './index'
import { ccApi } from '../../api/ccClient'
import { colors, fonts, spacing } from '../../shell/tokens'
import EmptyState from '../../shell/EmptyState'
import CollapsibleSessionContext from './CollapsibleSessionContext'
import { useWsAutoReconnect } from '../../lib/wsAutoReconnect'
import ConnectionStatus from '../../components/ConnectionStatus'

interface XtermLib {
  Terminal: any
  FitAddon: any
  WebLinksAddon: any
}

let _xtermPromise: Promise<XtermLib> | null = null
async function loadXterm(): Promise<XtermLib> {
  if (_xtermPromise) return _xtermPromise
  _xtermPromise = (async () => {
    const [{ Terminal }, fitMod, webLinksMod] = await Promise.all([
      import('@xterm/xterm'),
      import('@xterm/addon-fit'),
      import('@xterm/addon-web-links'),
    ])
    // @ts-ignore — CSS side-effect import; vite handles it.
    await import('@xterm/xterm/css/xterm.css')
    return {
      Terminal,
      FitAddon: fitMod.FitAddon,
      WebLinksAddon: webLinksMod.WebLinksAddon,
    }
  })()
  return _xtermPromise
}

const S: Record<string, any> = {
  root: { display: 'flex', flexDirection: 'column' as const, height: '100%', background: colors.bg, color: colors.text, fontFamily: fonts.mono, fontSize: 14 },
  body: { flex: 1, display: 'flex', minHeight: 0 },
  termCol: { flex: 1, display: 'flex', flexDirection: 'column' as const, minWidth: 0 },
  header: {
    padding: `${spacing.xs}px ${spacing.lg}px`, borderBottom: `1px solid ${colors.border}`,
    background: colors.bgPanel, display: 'flex', alignItems: 'center', gap: spacing.lg, flexShrink: 0,
  },
  meta: { color: colors.textFaint, fontSize: 14, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  status: (alive: boolean): React.CSSProperties => ({
    color: alive ? '#4caf50' : '#666', fontSize: 14, fontWeight: 600 as const,
  }),
  killBtn: {
    padding: '2px 8px', background: 'transparent', color: '#ef5350',
    border: `1px solid #4a2a2a`, borderRadius: 3, cursor: 'pointer', fontSize: 14, fontFamily: fonts.mono,
  },
  termWrap: { flex: 1, overflow: 'hidden', padding: spacing.xs, minHeight: 0 },
  errorBar: {
    padding: spacing.md, background: '#2a1010', borderTop: '1px solid #4a2a2a',
    color: '#ef5350', fontSize: 14, flexShrink: 0,
  },
}

export default function CcSessionEditor({ entity }: { entity: CcSessionEntity }) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const termRef = useRef<any>(null)
  const fitRef = useRef<any>(null)
  const xtermLoadedRef = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const [alive, setAlive] = useState<boolean>(entity.alive)

  // 1) 加载 xterm 库 (一次, entity.id 变也不重建 — 重建会闪烁)
  useEffect(() => {
    let cancelled = false
    let resizeObs: ResizeObserver | null = null
    let pendingDispose: (() => void) | null = null

    ;(async () => {
      try {
        const { Terminal, FitAddon, WebLinksAddon } = await loadXterm()
        if (cancelled) return
        if (!containerRef.current) return
        if (xtermLoadedRef.current) return

        const term = new Terminal({
          fontFamily: 'Consolas, "Cascadia Code", Menlo, monospace',
          fontSize: 15,
          cursorBlink: true,
          cursorStyle: 'bar',
          theme: {
            background: '#0f0f0f', foreground: '#e0e0e0', cursor: '#90caf9',
            selectionBackground: '#1a2a3a',
          },
          scrollback: 5000,
          convertEol: false,
          allowProposedApi: false,
        })
        const fit = new FitAddon()
        term.loadAddon(fit)
        term.loadAddon(new WebLinksAddon())
        term.open(containerRef.current)
        try { fit.fit() } catch { /* size 0 race */ }
        termRef.current = term
        fitRef.current = fit
        xtermLoadedRef.current = true

        resizeObs = new ResizeObserver(() => {
          if (!fit || !term) return
          try {
            fit.fit()
            // resize 帧通过 wsConn.send (state 不在闭包内, 用 ref 取)
            wsConnSendRef.current?.(JSON.stringify({
              type: 'resize', cols: term.cols, rows: term.rows,
            }))
          } catch { /* */ }
        })
        resizeObs.observe(containerRef.current)

        // 终端输入 → ws (经 wsAutoReconnect 队列, 重连期间排队 open 后补发)
        const disp = term.onData((data: string) => {
          wsConnSendRef.current?.(JSON.stringify({ type: 'input', data }))
        })
        pendingDispose = () => disp.dispose()
      } catch (e) {
        if (!cancelled) setError(String(e))
      }
    })()

    return () => {
      cancelled = true
      try { resizeObs?.disconnect() } catch { /* */ }
      try { pendingDispose?.() } catch { /* */ }
      try { termRef.current?.dispose() } catch { /* */ }
      termRef.current = null
      fitRef.current = null
      xtermLoadedRef.current = false
    }
  }, [])

  // 2) WebSocket 自愈 — 重连后 clear term 重写 snapshot, 避免 ring-buffer 重写视觉重复
  const wsConnSendRef = useRef<((data: string) => void) | null>(null)

  const handleMessage = useCallback((ev: MessageEvent) => {
    let msg: any
    try { msg = JSON.parse(ev.data as string) } catch { return }
    const term = termRef.current
    if (!term) return
    if (msg.type === 'snapshot' && Array.isArray(msg.chunks)) {
      // 重连时也会重发 snapshot — 先 clear 再 write 避免视觉重复
      try { term.clear() } catch { /* */ }
      for (const c of msg.chunks) term.write(c)
    } else if (msg.type === 'output' && typeof msg.data === 'string') {
      term.write(msg.data)
    } else if (msg.type === 'exit') {
      setAlive(false)
      term.write(`\r\n\x1b[33m[session ended: ${msg.reason || 'unknown'}]\x1b[0m\r\n`)
    }
  }, [])

  const handleOpen = useCallback((_ws: WebSocket, isReconnect: boolean) => {
    setError(null)
    // open 时立即同步 term size 给后端
    const term = termRef.current
    const fit = fitRef.current
    if (term && fit) {
      try {
        fit.fit()
        wsConnSendRef.current?.(JSON.stringify({
          type: 'resize', cols: term.cols, rows: term.rows,
        }))
      } catch { /* */ }
    }
    if (isReconnect) {
      term?.write('\r\n\x1b[36m[reconnected · 历史已续展]\x1b[0m\r\n')
    }
  }, [])

  const wsConn = useWsAutoReconnect({
    url: ccApi.wsUrl(entity.id),
    onMessage: handleMessage,
    onOpen: handleOpen,
  })

  // expose wsConn.send to ref (xterm 加载 effect 运行时尚没有 wsConn)
  useEffect(() => { wsConnSendRef.current = wsConn.send }, [wsConn.send])

  const onKill = async () => {
    try {
      await ccApi.kill(entity.id)
      setAlive(false)
    } catch (e) {
      setError(`kill failed: ${e}`)
    }
  }

  return (
    <div style={S.root} data-cc-session-id={entity.id}>
      <div style={S.header}>
        <div style={S.meta} title={entity.cwd}>
          {entity.cmd.join(' ')} · cwd={entity.cwd}
        </div>
        <span style={S.status(alive)} data-cc-status>{alive ? '● alive' : '○ ended'}</span>
        <ConnectionStatus
          state={wsConn.state}
          reconnectAttempts={wsConn.reconnectAttempts}
          disconnectedAt={wsConn.disconnectedAt}
          label="pty"
        />
        <button style={S.killBtn} onClick={onKill} disabled={!alive} data-cc-kill>kill</button>
      </div>
      <div style={S.body}>
        <div style={S.termCol}>
          <div ref={containerRef} style={S.termWrap} data-cc-term />
          {error && <div style={S.errorBar}>{error}</div>}
          {error && !alive && <EmptyState text="重新打开 tab 可重连" />}
        </div>
        <CollapsibleSessionContext sessionId={entity.id} alive={alive} />
      </div>
    </div>
  )
}
