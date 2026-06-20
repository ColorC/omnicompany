# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""真正全面 e2e — 校对所有元素所有属性, 不预设, 让数据说话.

用户 2026-05-13 立: "校对所有元素的所有属性, 所有, 每一个按钮, 每一个元素".

记录:
- MutationObserver 全程 DOM 变更 (每次 chat-message 增删都拍 snapshot)
- 所有 ws lifecycle event
- 所有 postMessage __omnichat 信号
- 多轮发消息后, 列出整个 DOM tree (按钮 / select / input / 状态显示 等) 跟期望对比
- 是否有 entity 切换 (ws url 切换 = 切了)
- TokenUsagePie 数值轨迹 (title)
- 是否有 button 出现两次 / 重复 chat-message / 重复 toolbar

跑出来打全报告. 不打 PASS/FAIL 总结 — 让人读完所有数据自己判断.
"""
import json, time
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8210/chat-standalone"

INSTRUMENT = """
window.__obs = {
  msgSnapshots: [],
  wsEvents: [],
  postMessages: [],
  consoleErrors: [],
}

function chatSnap(label) {
  const msgs = Array.from(document.querySelectorAll('.chat-message')).map(m => ({
    cls: m.className.slice(0, 80),
    text: (m.textContent || '').trim(),
  }))
  window.__obs.msgSnapshots.push({ t: Date.now(), label, count: msgs.length, msgs })
}

const mo = new MutationObserver(() => chatSnap('mut'))
function startObs() {
  const root = document.querySelector('[data-testid="chat-standalone-root"]')
  if (root) { mo.observe(root, { childList: true, subtree: true, characterData: true }); chatSnap('start') }
  else setTimeout(startObs, 100)
}
startObs()

const origWS = window.WebSocket
window.WebSocket = function(...args) {
  const ws = new origWS(...args)
  window.__obs.wsEvents.push({ t: Date.now(), kind: 'create', url: args[0] })
  ws.addEventListener('open', () => window.__obs.wsEvents.push({ t: Date.now(), kind: 'open', url: args[0] }))
  ws.addEventListener('close', (ev) => window.__obs.wsEvents.push({ t: Date.now(), kind: 'close', code: ev.code, reason: ev.reason, url: args[0] }))
  return ws
}
Object.setPrototypeOf(window.WebSocket, origWS)
window.WebSocket.prototype = origWS.prototype
window.WebSocket.OPEN = origWS.OPEN
window.WebSocket.CLOSED = origWS.CLOSED

const origPM = window.postMessage
window.postMessage = function(...args) {
  if (args[0] && args[0].__omnichat) window.__obs.postMessages.push({ t: Date.now(), ...args[0] })
  return origPM.apply(window, args)
}
"""


def dump_ui_state(page, label):
    """完整拍当前页所有 ChatStandalone 元素."""
    return page.evaluate("""(label) => {
      const root = document.querySelector('[data-testid="chat-standalone-root"]')
      if (!root) return { label, root: null }
      // 所有 button + 文字 + disabled
      const buttons = Array.from(root.querySelectorAll('button')).map(b => ({
        text: (b.textContent || '').trim().slice(0, 50),
        disabled: b.disabled,
        title: b.title || null,
        testId: b.getAttribute('data-testid') || null,
      }))
      // 所有 select + 当前值 + 选项
      const selects = Array.from(root.querySelectorAll('select')).map(s => ({
        testId: s.getAttribute('data-testid') || null,
        value: s.value,
        options: Array.from(s.options).map(o => ({ value: o.value, text: o.text })),
        disabled: s.disabled,
      }))
      // 所有 input + 当前值
      const inputs = Array.from(root.querySelectorAll('input, textarea')).map(i => ({
        tag: i.tagName,
        testId: i.getAttribute('data-testid') || null,
        type: i.type,
        value: i.value,
        placeholder: i.placeholder,
        disabled: i.disabled,
      }))
      // chat-messages 全文 + role
      const msgs = Array.from(root.querySelectorAll('.chat-message')).map(m => ({
        role: m.className.includes('user') ? 'user' :
              m.className.includes('assistant') ? 'assistant' :
              m.className.includes('error') ? 'error' : '?',
        text: (m.textContent || '').trim(),
      }))
      // TokenUsagePie title (used/total)
      const tokenTitle = Array.from(root.querySelectorAll('span[title]'))
        .find(s => /tokens/.test(s.title || ''))?.title || null
      // 顶栏 brand
      const brand = root.querySelector('[data-testid="chat-standalone-brand"]')?.textContent || null
      return { label, buttons, selects, inputs, msgs, tokenTitle, brand }
    }""", label)


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(viewport={"width": 1100, "height": 900}).new_page()
    page.on('pageerror', lambda e: page.evaluate(f"() => window.__obs.consoleErrors.push({json.dumps(str(e))})"))
    page.on('console', lambda m: page.evaluate(f"() => window.__obs.consoleErrors.push({json.dumps(m.text[:200])})") if m.type == 'error' else None)
    page.add_init_script(INSTRUMENT)

    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    states = []
    states.append(dump_ui_state(page, 'after_load'))

    # 新建 session
    page.click('[data-testid="chat-standalone-new-session"]')
    page.wait_for_timeout(3500)
    states.append(dump_ui_state(page, 'after_create_session'))

    # 多轮发消息
    turns = ["hi", "1+1=?", "讲一句话总结上面对话"]
    for i, t in enumerate(turns, 1):
        page.locator('textarea').first.fill(t)
        page.locator('textarea').first.press("Control+Enter")
        try:
            page.wait_for_function(
                f"""(prev) => {{
                  const m = document.querySelectorAll('.chat-message')
                  let asst = 0
                  m.forEach(x => {{ if (x.className.includes('assistant')) asst++ }})
                  return asst >= prev
                }}""",
                arg=i,
                timeout=90_000,
            )
        except Exception as e:
            print(f"turn {i} wait failed: {e}")
        page.wait_for_timeout(3500)
        states.append(dump_ui_state(page, f'after_turn_{i}'))

    obs = page.evaluate("() => window.__obs")
    b.close()

# 全部 dump 出来 — 同时写到文件 (Windows GBK stdout 顶不住 unicode)
import sys, io
out_file = open("e2e_total_report.txt", "w", encoding="utf-8")
class Tee:
    def __init__(self, *streams): self.streams = streams
    def write(self, s):
        for st in self.streams:
            try: st.write(s)
            except UnicodeEncodeError: st.write(s.encode('ascii', 'replace').decode('ascii'))
    def flush(self):
        for st in self.streams:
            try: st.flush()
            except Exception: pass
sys.stdout = Tee(sys.stdout, out_file)

print("=" * 80)
print("WS LIFECYCLE EVENTS")
print("=" * 80)
for ev in obs['wsEvents']:
    print(f"  {ev}")
ws_creates = sum(1 for ev in obs['wsEvents'] if ev['kind'] == 'create')
ws_opens = sum(1 for ev in obs['wsEvents'] if ev['kind'] == 'open')
ws_closes = sum(1 for ev in obs['wsEvents'] if ev['kind'] == 'close')
print(f"\n  TOTAL: create={ws_creates} open={ws_opens} close={ws_closes}")
print(f"  独立 url 数: {len(set(ev.get('url') for ev in obs['wsEvents']))}")

print("\n" + "=" * 80)
print("POSTMESSAGE __omnichat 事件")
print("=" * 80)
for pm in obs['postMessages']:
    print(f"  {pm}")

print("\n" + "=" * 80)
print("CONSOLE ERRORS")
print("=" * 80)
for e in obs['consoleErrors']:
    print(f"  {e}")

print("\n" + "=" * 80)
print("CHAT-MESSAGE COUNT 时间线")
print("=" * 80)
last = -1
for s in obs['msgSnapshots']:
    if s['count'] != last:
        print(f"  t={s['t']} {s['label']}: count={s['count']}")
        last = s['count']

print("\n" + "=" * 80)
print("各阶段 UI 完整状态")
print("=" * 80)
for st in states:
    print(f"\n--- {st['label']} ---")
    print(f"brand: {st.get('brand')!r}")
    print(f"tokenTitle: {st.get('tokenTitle')!r}")
    print(f"selects ({len(st.get('selects', []))}):")
    for s in st.get('selects', []):
        print(f"  {s['testId']}: value={s['value']!r}, opts={len(s['options'])}")
    print(f"inputs ({len(st.get('inputs', []))}):")
    for i in st.get('inputs', []):
        print(f"  {i['tag']} {i['testId']}: value={i['value']!r}")
    print(f"buttons ({len(st.get('buttons', []))}):")
    for btn in st.get('buttons', []):
        print(f"  {btn['testId']}: {btn['text']!r} disabled={btn['disabled']}")
    print(f"msgs ({len(st.get('msgs', []))}):")
    for m in st.get('msgs', []):
        print(f"  [{m['role']}] {m['text'][:120]!r}")
