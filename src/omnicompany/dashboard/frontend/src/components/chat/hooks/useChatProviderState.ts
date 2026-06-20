import { useCallback, useEffect, useRef, useState } from 'react';
import { authenticatedFetch } from '../../../utils/api';
import { CLAUDE_MODELS, CODEX_MODELS, CURSOR_MODELS, GEMINI_MODELS } from '../../../shared/modelConstants';
import type { PendingPermissionRequest, PermissionMode } from '../types/types';
import type { ProjectSession, LLMProvider } from '../../../types/app';

const getPermissionModesForProvider = (provider: LLMProvider): PermissionMode[] => {
  if (provider === 'codex') {
    return ['default', 'acceptEdits', 'bypassPermissions'];
  }
  if (provider === 'claude') {
    return ['default', 'auto', 'acceptEdits', 'bypassPermissions', 'plan'];
  }
  return ['default', 'acceptEdits', 'bypassPermissions', 'plan'];
};

interface UseChatProviderStateArgs {
  selectedSession: ProjectSession | null;
  onPermissionModeChange?: (mode: PermissionMode) => void;
}

export function useChatProviderState({ selectedSession, onPermissionModeChange }: UseChatProviderStateArgs) {
  // 默认最大权限(无限制): 用户明示 omnidashboard 默认 bypassPermissions, 不逐条问。
  const [permissionMode, setPermissionMode] = useState<PermissionMode>('bypassPermissions');
  const [pendingPermissionRequests, setPendingPermissionRequests] = useState<PendingPermissionRequest[]>([]);
  const [provider, setProvider] = useState<LLMProvider>(() => {
    return (localStorage.getItem('selected-provider') as LLMProvider) || 'claude';
  });
  const [cursorModel, setCursorModel] = useState<string>(() => {
    return localStorage.getItem('cursor-model') || CURSOR_MODELS.DEFAULT;
  });
  const [claudeModel, setClaudeModel] = useState<string>(() => {
    return localStorage.getItem('claude-model') || CLAUDE_MODELS.DEFAULT;
  });
  const [codexModel, setCodexModel] = useState<string>(() => {
    const saved = localStorage.getItem('codex-model');
    return saved && CODEX_MODELS.OPTIONS.some((model: { value: string }) => model.value === saved)
      ? saved
      : CODEX_MODELS.DEFAULT;
  });
  const [geminiModel, setGeminiModel] = useState<string>(() => {
    return localStorage.getItem('gemini-model') || GEMINI_MODELS.DEFAULT;
  });

  const lastProviderRef = useRef(provider);

  useEffect(() => {
    if (!selectedSession?.id) {
      return;
    }

    const savedMode = localStorage.getItem(`permissionMode-${selectedSession.id}`) as PermissionMode | null;
    const validModes = getPermissionModesForProvider(provider);
    // 没有会话级保存值时, 回退到最大权限(无限制), 而非 default。
    setPermissionMode(savedMode && validModes.includes(savedMode) ? savedMode : 'bypassPermissions');
  }, [selectedSession?.id, provider]);

  useEffect(() => {
    if (!selectedSession?.__provider || selectedSession.__provider === provider) {
      return;
    }

    setProvider(selectedSession.__provider);
    localStorage.setItem('selected-provider', selectedSession.__provider);
  }, [provider, selectedSession]);

  useEffect(() => {
    if (lastProviderRef.current === provider) {
      return;
    }
    setPendingPermissionRequests([]);
    lastProviderRef.current = provider;
  }, [provider]);

  useEffect(() => {
    setPendingPermissionRequests((previous) =>
      previous.filter((request) => !request.sessionId || request.sessionId === selectedSession?.id),
    );
  }, [selectedSession?.id]);

  useEffect(() => {
    if (provider !== 'cursor') {
      return;
    }

    authenticatedFetch('/api/cursor/config')
      .then((response) => response.json())
      .then((data) => {
        if (!data.success || !data.config?.model?.modelId) {
          return;
        }

        const modelId = data.config.model.modelId as string;
        if (!localStorage.getItem('cursor-model')) {
          setCursorModel(modelId);
        }
      })
      .catch((error) => {
        console.error('Error loading Cursor config:', error);
      });
  }, [provider]);

  const cyclePermissionMode = useCallback(() => {
    const modes = getPermissionModesForProvider(provider);

    const currentIndex = modes.indexOf(permissionMode);
    const nextIndex = (currentIndex + 1) % modes.length;
    const nextMode = modes[nextIndex];
    setPermissionMode(nextMode);

    if (selectedSession?.id) {
      localStorage.setItem(`permissionMode-${selectedSession.id}`, nextMode);
    }
    onPermissionModeChange?.(nextMode);
  }, [onPermissionModeChange, permissionMode, provider, selectedSession?.id]);

  return {
    provider,
    setProvider,
    cursorModel,
    setCursorModel,
    claudeModel,
    setClaudeModel,
    codexModel,
    setCodexModel,
    geminiModel,
    setGeminiModel,
    permissionMode,
    setPermissionMode,
    pendingPermissionRequests,
    setPendingPermissionRequests,
    cyclePermissionMode,
  };
}
