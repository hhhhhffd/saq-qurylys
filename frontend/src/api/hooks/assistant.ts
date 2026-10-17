import { useQuery } from '@tanstack/react-query';
import { api, ApiError } from '../client';
import { qk } from '../keys';

interface AssistantConfig {
  enabled: boolean;
  model: string;
}

/** The module is optional: a 404 on its config means it is switched off. The query resolves to `null` then. */
function useAssistantConfig() {
  return useQuery({
    queryKey: qk.assistantConfig,
    queryFn: async () => {
      try {
        return await api<AssistantConfig>('/assistant/config');
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 5 * 60_000,
  });
}

/** True only once the config arrived and says the assistant is on (header button and panel). */
export function useAssistantEnabled(): boolean {
  const { data } = useAssistantConfig();
  return data?.enabled === true;
}
