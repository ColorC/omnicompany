/**
 * Clean-view 折叠 (学习 codex 的对话呈现):
 * 默认隐藏一轮回复里的"中间工作记录"(工具调用 / 思考 / 中间文本 / 上下文事件),
 * 只保留每一轮的「最后一段文本输出」以及必须可见的关键消息(错误、交互式追问、后台任务通知)。
 * 被折叠的工作会聚成一个可展开的 fold 节点, 放在该轮最终文本之前。
 *
 * 纯函数, 不依赖 React —— 方便单测。输入是 normalize 后的 ChatMessage[](见 useChatMessages),
 * 输出是渲染层用的显示项数组。
 */
import type { ChatMessage } from '../types/types';

export type CleanDisplayItem =
  | { kind: 'msg'; message: ChatMessage; prev: ChatMessage | null }
  | { kind: 'fold'; id: string; messages: ChatMessage[] };

/** 普通助手文本(可流式): 这就是我们要保留的"最后一段"的候选。 */
function isPlainAssistantText(m: ChatMessage): boolean {
  if (m.type !== 'assistant') return false;
  if (m.isToolUse || m.isThinking || m.isInteractivePrompt || m.isTaskNotification || m.isContextNotification) {
    return false;
  }
  return Boolean((m.content || '').trim());
}

/** 关键消息: 无论精简与否都必须可见(错误 / 交互式追问 / 后台任务通知)。 */
function isCritical(m: ChatMessage): boolean {
  return m.type === 'error' || Boolean(m.isInteractivePrompt) || Boolean(m.isTaskNotification);
}

function keyOf(m: ChatMessage, fallback: number): string {
  return String(m.id ?? `idx${fallback}`);
}

export function buildCleanView(messages: ChatMessage[]): CleanDisplayItem[] {
  const out: CleanDisplayItem[] = [];
  let prevShown: ChatMessage | null = null;

  const pushMsg = (m: ChatMessage) => {
    out.push({ kind: 'msg', message: m, prev: prevShown });
    prevShown = m;
  };

  let i = 0;
  while (i < messages.length) {
    const m = messages[i];
    // 用户消息永远单独保留, 也作为一轮的边界。
    if (m.type === 'user') {
      pushMsg(m);
      i++;
      continue;
    }

    // 收集一轮助手回复 = 连续的非 user 消息。
    let j = i;
    const turn: ChatMessage[] = [];
    while (j < messages.length && messages[j].type !== 'user') {
      turn.push(messages[j]);
      j++;
    }

    // 该轮里"最后一段文本"的位置 —— 只保留它, 之前的文本一并折叠。
    let lastTextIdx = -1;
    for (let k = 0; k < turn.length; k++) {
      if (isPlainAssistantText(turn[k])) lastTextIdx = k;
    }

    let buf: ChatMessage[] = [];
    const flush = () => {
      if (buf.length) {
        out.push({ kind: 'fold', id: `${keyOf(buf[0], i)}:fold:${buf.length}`, messages: buf });
        buf = [];
      }
    };

    for (let k = 0; k < turn.length; k++) {
      const x = turn[k];
      const keep = isCritical(x) || k === lastTextIdx;
      if (keep) {
        flush();
        pushMsg(x);
      } else {
        buf.push(x);
      }
    }
    flush();

    i = j;
  }

  return out;
}
