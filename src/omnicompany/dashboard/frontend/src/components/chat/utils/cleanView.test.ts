import { describe, it, expect } from 'vitest';
import { buildCleanView } from './cleanView';
import type { ChatMessage } from '../types/types';

const user = (id: string, content = 'hi'): ChatMessage => ({ id, type: 'user', content, timestamp: 0 });
const text = (id: string, content: string): ChatMessage => ({ id, type: 'assistant', content, timestamp: 0 });
const tool = (id: string, toolName: string): ChatMessage => ({ id, type: 'assistant', content: '', timestamp: 0, isToolUse: true, toolName });
const thinking = (id: string): ChatMessage => ({ id, type: 'assistant', content: 'hmm', timestamp: 0, isThinking: true });
const err = (id: string): ChatMessage => ({ id, type: 'error', content: 'boom', timestamp: 0 });
const prompt = (id: string): ChatMessage => ({ id, type: 'assistant', content: '?', timestamp: 0, isInteractivePrompt: true });

describe('buildCleanView', () => {
  it('folds intermediate tools/thinking/mid-text, keeps user + final text of a turn', () => {
    const items = buildCleanView([
      user('u1'),
      tool('t1', 'Read'),
      thinking('th1'),
      text('m1', 'let me check...'),
      tool('t2', 'Bash'),
      text('f1', 'done, here is the result'),
    ]);
    expect(items.map((i) => i.kind)).toEqual(['msg', 'fold', 'msg']);
    expect((items[0] as any).message.id).toBe('u1');
    expect((items[1] as any).messages).toHaveLength(4); // t1, th1, m1, t2
    expect((items[2] as any).message.id).toBe('f1');
  });

  it('keeps critical messages (error / interactive prompt) visible', () => {
    const items = buildCleanView([
      user('u1'),
      tool('t1', 'Bash'),
      err('e1'),
      text('f1', 'final'),
    ]);
    expect(items.map((i) => i.kind)).toEqual(['msg', 'fold', 'msg', 'msg']);
    expect((items[2] as any).message.id).toBe('e1');
    expect((items[3] as any).message.id).toBe('f1');

    const withPrompt = buildCleanView([user('u1'), tool('t1', 'Read'), prompt('p1')]);
    expect(withPrompt.map((i) => i.kind)).toEqual(['msg', 'fold', 'msg']);
    expect((withPrompt[2] as any).message.id).toBe('p1');
  });

  it('a tool-only (in-progress) turn becomes a single fold', () => {
    const items = buildCleanView([user('u1'), tool('t1', 'Read'), tool('t2', 'Grep')]);
    expect(items.map((i) => i.kind)).toEqual(['msg', 'fold']);
    expect((items[1] as any).messages).toHaveLength(2);
  });

  it('only the LAST text segment of a turn is kept; earlier text folds', () => {
    const items = buildCleanView([
      user('u1'),
      text('a', 'first segment'),
      text('b', 'second segment'),
      text('c', 'final segment'),
    ]);
    // a, b folded; c kept
    expect(items.map((i) => i.kind)).toEqual(['msg', 'fold', 'msg']);
    expect((items[1] as any).messages.map((m: ChatMessage) => m.id)).toEqual(['a', 'b']);
    expect((items[2] as any).message.id).toBe('c');
  });

  it('passes through plain user/text conversations without spurious folds', () => {
    const items = buildCleanView([user('u1'), text('a', 'hello'), user('u2'), text('b', 'world')]);
    expect(items.map((i) => i.kind)).toEqual(['msg', 'msg', 'msg', 'msg']);
  });
});
