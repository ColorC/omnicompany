/**
 * wsAutoReconnect — 通用 WebSocket 自动重连 hook.
 *
 * 配合 [2026-05-09]DASHBOARD-DOGFOOD-RESILIENCE 道路使用. 浏览器跟 dashboard
 * 的 WebSocket 桥接在以下场景会断:
 *
 *  1. dashboard 进程被 file watcher reload (改了 controlplane 任意文件)
 *  2. ccdaemon 进程被显式 restart (`omni cc daemon restart`)
 *  3. 网络抖动 / 浏览器休眠
 *
 * 这个 hook 接管断开后的重连逻辑, 用指数退避 (1s → 2s → 4s → 8s → 30s 上限).
 * 重连成功后调用 onReconnect, 业务代码应当在那里发请求拉 snapshot 续展历史.
 *
 * 设计要点:
 * - 不在 WebSocket 上多包一层抽象 — 暴露真 WebSocket 给业务用 (send / readyState)
 * - 主动 close (code=1000) 视作"用户故意停止重连", 不再 reconnect
 * - 累计 reconnecting > 60s 或 >5 次记 longDisconnect, 业务侧 UI 提示用户
 * - 待发送队列: reconnecting 期间用户输入入队, 重连成功后顺序补发
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export type WsConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected'

export interface WsAutoReconnectOptions {
  url: string
  /** 断开时收到的 close.code === intentionalCloseCode 不再重连 (默认 1000). */
  intentionalCloseCode?: number
  /** 重连退避基准 ms, 实际 = base * 2^attempt, 上限 maxBackoffMs. */
  baseBackoffMs?: number
  maxBackoffMs?: number
  /** 持续无法连超过此值, state 变 disconnected (默认 60s). 业务侧应弹提示. */
  longDisconnectMs?: number
  /** 收 server frame. */
  onMessage?: (ev: MessageEvent) => void
  /** 每次连接 open 时调用 (无论首次还是重连). */
  onOpen?: (ws: WebSocket, isReconnect: boolean) => void
  /** 关闭时调用 (无论是否会重连). */
  onClose?: (ev: CloseEvent) => void
  /** 出错时调用. */
  onError?: (ev: Event) => void
}

export interface WsAutoReconnectHandle {
  state: WsConnectionState
  /** reconnect 累计次数, 重连成功后归零. */
  reconnectAttempts: number
  /** 最近一次 disconnect 起始时间 ms (Date.now). 仅在 state !== connected 时有意义. */
  disconnectedAt: number | null
  /** 当前 WebSocket 实例 (可能是 null, 或处于任意 readyState). */
  ws: WebSocket | null
  /** 发送 — open 时直发, 否则进队列等重连. */
  send: (data: string | ArrayBuffer | Blob) => void
  /** 主动停止重连 (code=1000), 业务侧组件 unmount 时也要调. */
  close: (code?: number, reason?: string) => void
}

export function useWsAutoReconnect(opts: WsAutoReconnectOptions): WsAutoReconnectHandle {
  const {
    url,
    intentionalCloseCode = 1000,
    baseBackoffMs = 1000,
    maxBackoffMs = 30_000,
    longDisconnectMs = 60_000,
    onMessage,
    onOpen,
    onClose,
    onError,
  } = opts

  const [state, setState] = useState<WsConnectionState>('connecting')
  const [reconnectAttempts, setReconnectAttempts] = useState(0)
  const [disconnectedAt, setDisconnectedAt] = useState<number | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const longDisconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const intentionalCloseRef = useRef(false)
  const queueRef = useRef<(string | ArrayBuffer | Blob)[]>([])
  // capture latest callbacks without re-running the connect effect
  const onMessageRef = useRef(onMessage)
  const onOpenRef = useRef(onOpen)
  const onCloseRef = useRef(onClose)
  const onErrorRef = useRef(onError)
  useEffect(() => { onMessageRef.current = onMessage }, [onMessage])
  useEffect(() => { onOpenRef.current = onOpen }, [onOpen])
  useEffect(() => { onCloseRef.current = onClose }, [onClose])
  useEffect(() => { onErrorRef.current = onError }, [onError])

  const cleanupTimers = () => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (longDisconnectTimerRef.current !== null) {
      clearTimeout(longDisconnectTimerRef.current)
      longDisconnectTimerRef.current = null
    }
  }

  const connect = useCallback((isReconnect: boolean, attempt: number) => {
    if (intentionalCloseRef.current) return
    setState(isReconnect ? 'reconnecting' : 'connecting')

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setState('connected')
      setReconnectAttempts(0)
      setDisconnectedAt(null)
      cleanupTimers()
      // 排队消息按顺序发出
      while (queueRef.current.length > 0) {
        const msg = queueRef.current.shift()!
        try {
          ws.send(msg)
        } catch {
          queueRef.current.unshift(msg)
          break
        }
      }
      onOpenRef.current?.(ws, isReconnect)
    }

    ws.onmessage = (ev) => {
      onMessageRef.current?.(ev)
    }

    ws.onerror = (ev) => {
      onErrorRef.current?.(ev)
    }

    ws.onclose = (ev) => {
      onCloseRef.current?.(ev)
      if (intentionalCloseRef.current || ev.code === intentionalCloseCode) {
        setState('disconnected')
        return
      }
      if (disconnectedAt === null) {
        setDisconnectedAt(Date.now())
        // longDisconnect 状态切换: 60s 后没连上变 disconnected (UI 提示)
        longDisconnectTimerRef.current = setTimeout(() => {
          setState((prev) => (prev === 'reconnecting' ? 'disconnected' : prev))
        }, longDisconnectMs)
      }
      // 调度下一次重连
      const nextAttempt = attempt + 1
      setReconnectAttempts(nextAttempt)
      const backoff = Math.min(baseBackoffMs * 2 ** (nextAttempt - 1), maxBackoffMs)
      setState('reconnecting')
      timerRef.current = setTimeout(() => {
        connect(true, nextAttempt)
      }, backoff)
    }
  }, [url, intentionalCloseCode, baseBackoffMs, maxBackoffMs, longDisconnectMs, disconnectedAt])

  useEffect(() => {
    intentionalCloseRef.current = false
    queueRef.current = []
    setReconnectAttempts(0)
    setDisconnectedAt(null)
    connect(false, 0)

    return () => {
      intentionalCloseRef.current = true
      cleanupTimers()
      const ws = wsRef.current
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        try { ws.close(intentionalCloseCode, 'unmount') } catch { /* */ }
      }
      wsRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url])  // url 变 → 重新接

  const send = useCallback((data: string | ArrayBuffer | Blob) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(data)
    } else {
      // open 后会自动 flush
      queueRef.current.push(data)
    }
  }, [])

  const close = useCallback((code = 1000, reason = 'closed-by-app') => {
    intentionalCloseRef.current = true
    cleanupTimers()
    const ws = wsRef.current
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      try { ws.close(code, reason) } catch { /* */ }
    }
    setState('disconnected')
  }, [])

  return {
    state,
    reconnectAttempts,
    disconnectedAt,
    ws: wsRef.current,
    send,
    close,
  }
}
