# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""综合 e2e — 多轮真实工作流 + MutationObserver 全量记录 + 精确校验.

不预设"应该多少条". 跑完打全部观察, 让数据说话, 再判断哪里不对.

工作流:
  1. 创 session
  2. 发"hi" 等回复
  3. 发"算 1+1 等于几" 等回复
  4. 发"列出当前目录文件" (触发工具)
  5. 整轮过程中 MutationObserver 每秒抓 chat-message 数 + 内容 hash + ws 状态
  6. 收尾打: 各时刻 chat-message 数, 是否有"消失再出现"的现象, 用户消息是否都在, assistant 重复率
"""
import time
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8210/chat-standalone"


# 注入 init script 装记录器 — 所有 chat-message 变化都记下来
INSTRUMENT = """
window.__obs = {
  msgSnapshots: [],     // 每次 chat-message 数变化时记录: { t, count, contents }
  wsEvents: [],         // ws open/close/error 全记
  wsInstances: [],
  postMessages: [],     // ChatStandalone postMessage 到 top 的全记
}

function snapshot(label) {
  const msgs = Array.from(document.querySelectorAll('.chat-message')).map(m => ({
    role: m.className.includes('user') ? 'user' :
          m.className.includes('assistant') ? 'assistant' :
          m.className.includes('error') ? 'error' : '?',
    text: (m.textContent || '').trim().slice(0, 80),
  }))
  window.__obs.msgSnapshots.push({
    t: Date.now(),
    label,
    count: msgs.length,
    msgs,
  })
}

// MutationObserver — 每次 .chat-message 子树变就 snapshot
const mo = new MutationObserver(() => snapshot('mutation'))
function startObs() {
  const root = document.querySelector('[data-testid="chat-standalone-root"]')
  if (root) {
    mo.observe(root, { childList: true, subtree: true, characterData: true })
    snapshot('start')
  } else {
    setTimeout(startObs, 100)
  }
}
startObs()

// ws 包装
const origWS = window.WebSocket
window.WebSocket = function(...args) {
  const ws = new origWS(...args)
  window.__obs.wsInstances.push(ws)
  window.__obs.wsEvents.push({ t: Date.now(), kind: 'create', url: args[0] })
  ws.addEventListener('open', () => window.__obs.wsEvents.push({ t: Date.now(), kind: 'open', url: args[0] }))
  ws.addEventListener('close', (ev) => window.__obs.wsEvents.push({
    t: Date.now(), kind: 'close', code: ev.code, reason: ev.reason, url: args[0],
  }))
  ws.addEventListener('error', () => window.__obs.wsEvents.push({ t: Date.now(), kind: 'error', url: args[0] }))
  return ws
}
Object.setPrototypeOf(window.WebSocket, origWS)
window.WebSocket.prototype = origWS.prototype
window.WebSocket.OPEN = origWS.OPEN
window.WebSocket.CLOSED = origWS.CLOSED

// postMessage 抓: parent webview 收 omnichat 消息
const origPostMessage = window.postMessage
window.postMessage = function(...args) {
  if (args[0] && args[0].__omnichat) {
    window.__obs.postMessages.push({ t: Date.now(), ...args[0] })
  }
  return origPostMessage.apply(window, args)
}
"""


def wait_assistant_reply_after(page, prev_assistant_count, timeout_ms=120_000):
    """等到 assistant 消息数比 prev_assistant_count 多至少 1 (一轮回完)."""
    page.wait_for_function(
        f"""() => {{
          const msgs = document.querySelectorAll('.chat-message')
          let asst = 0
          msgs.forEach(m => {{ if (m.className.includes('assistant')) asst++ }})
          return asst > {prev_assistant_count}
        }}""",
        timeout=timeout_ms,
    )


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(viewport={"width": 1100, "height": 900}).new_page()
    page.add_init_script(INSTRUMENT)

    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    page.click('[data-testid="chat-standalone-new-session"]')
    page.wait_for_timeout(3500)

    # 多轮工作流 (每轮发 → 等 → 记 → 再发)
    turns = [
        "hi",
        "请用 5 个字回答: 1+1 等于几",
        "请用 10 个字内简述这是什么对话",
    ]
    turn_marks = []
    prev_assistant_count = 0

    for i, msg in enumerate(turns, 1):
        page.evaluate(f"window.__obs = {{...window.__obs, mark_{i}_pre: Date.now()}}")
        turn_marks.append((f"turn_{i}_send", time.time()))
        print(f"\n=== Turn {i}: 发 {msg!r} ===")
        page.locator('textarea').first.fill(msg)
        page.locator('textarea').first.press("Control+Enter")
        try:
            wait_assistant_reply_after(page, prev_assistant_count, timeout_ms=90_000)
        except Exception as e:
            print(f"  WAIT TIMEOUT: {e}")
        page.wait_for_timeout(3500)  # 等 trailing frames
        turn_marks.append((f"turn_{i}_done", time.time()))

        cur_state = page.evaluate("""() => {
          const msgs = Array.from(document.querySelectorAll('.chat-message')).map(m => ({
            role: m.className.includes('user') ? 'user' :
                  m.className.includes('assistant') ? 'assistant' :
                  m.className.includes('error') ? 'error' : '?',
            text: (m.textContent || '').trim().slice(0, 100),
          }))
          let asst = 0, user = 0
          msgs.forEach(m => { if (m.role === 'assistant') asst++; else if (m.role === 'user') user++; })
          return { total: msgs.length, user, asst, msgs }
        }""")
        print(f"  当前: total={cur_state['total']} user={cur_state['user']} assistant={cur_state['asst']}")
        prev_assistant_count = cur_state['asst']
        for m in cur_state['msgs']:
            print(f"    [{m['role']}] {m['text']!r}")

    # 收尾: 整 observe 数据
    obs = page.evaluate("() => window.__obs")
    print("\n\n========== 收尾分析 ==========")
    print(f"总 ws 事件数: {len(obs['wsEvents'])}")
    for ev in obs['wsEvents'][:30]:
        print(f"  {ev}")
    print(f"\n总 ws instances: {len(obs['wsInstances'])} (期望 1: 一个 session 一条连接)")

    print(f"\n总 postMessage 事件: {len(obs['postMessages'])}")
    state_msgs = [pm for pm in obs['postMessages'] if pm.get('type') == 'session-state']
    print(f"  session-state: {len(state_msgs)}")
    state_seq = [pm.get('state') for pm in state_msgs]
    print(f"  state sequence: {state_seq}")

    print(f"\nMutationObserver 共记录 {len(obs['msgSnapshots'])} 个 snapshot")
    # 抓 count 突变 (减少/暴增)
    print("count 变化轨迹:")
    last_count = -1
    for s in obs['msgSnapshots']:
        if s['count'] != last_count:
            print(f"  t={s['t']} {s['label']}: count={s['count']}")
            last_count = s['count']

    # 检查重复内容
    print("\n=== 重复检测 ===")
    final_msgs = obs['msgSnapshots'][-1]['msgs'] if obs['msgSnapshots'] else []
    content_counts: dict[str, int] = {}
    for m in final_msgs:
        key = f"{m['role']}::{m['text']}"
        content_counts[key] = content_counts.get(key, 0) + 1
    dups = {k: v for k, v in content_counts.items() if v > 1}
    if dups:
        print("FAIL: 存在重复内容:")
        for k, v in dups.items():
            print(f"  {v}x  {k}")
    else:
        print("PASS: 无完全相同 role+content 重复")

    # 验所有用户消息都还在
    expected_user_texts = turns
    final_user_texts = [m['text'] for m in final_msgs if m['role'] == 'user']
    missing = []
    for exp in expected_user_texts:
        if not any(exp in t for t in final_user_texts):
            missing.append(exp)
    if missing:
        print(f"\nFAIL: 用户消息丢失: {missing}")
    else:
        print(f"\nPASS: {len(expected_user_texts)} 条用户消息都在")

    print(f"\n最终: total={len(final_msgs)} user={sum(1 for m in final_msgs if m['role']=='user')} assistant={sum(1 for m in final_msgs if m['role']=='assistant')}")
    b.close()
