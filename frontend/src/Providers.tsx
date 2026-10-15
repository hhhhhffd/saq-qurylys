import type { ReactNode } from 'react';
import { MantineProvider } from '@mantine/core';
import { DatesProvider } from '@mantine/dates';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { BrowserRouter } from 'react-router';
import 'dayjs/locale/ru';
import 'dayjs/locale/kk';
import { queryClient } from '@/api/queryClient';
import { AuthProvider } from '@/auth/AuthProvider';
import { cssVariablesResolver, theme } from '@/theme/theme';

export function Providers({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  return (
    <QueryClientProvider client={queryClient}>
      <MantineProvider
        theme={theme}
        cssVariablesResolver={cssVariablesResolver}
        defaultColorScheme="light"
        forceColorScheme="light"
      >
        <DatesProvider settings={{ locale: i18n.language === 'kk' ? 'kk' : 'ru', firstDayOfWeek: 1 }}>
          <ModalsProvider>
            <Notifications position="top-right" limit={4} />
            <BrowserRouter>
              <AuthProvider>{children}</AuthProvider>
            </BrowserRouter>
          </ModalsProvider>
        </DatesProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
}
