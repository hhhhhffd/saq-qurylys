import type { ReactNode } from 'react';
import { MantineProvider } from '@mantine/core';
import { DatesProvider } from '@mantine/dates';
import { QueryClientProvider } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { BrowserRouter } from 'react-router';
import 'dayjs/locale/ru';
import 'dayjs/locale/kk';
import { queryClient } from '@/api/queryClient';
import { AuthProvider } from '@/auth/AuthProvider';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ConfirmProvider } from '@/lib/confirm';
import { cssVariablesResolver, theme } from '@/theme/theme';

export function Providers({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  return (
    <QueryClientProvider client={queryClient}>
      <MantineProvider
        theme={theme}
        cssVariablesResolver={cssVariablesResolver}
        defaultColorScheme="dark"
        forceColorScheme="dark"
      >
        <DatesProvider settings={{ locale: i18n.language === 'kk' ? 'kk' : 'ru', firstDayOfWeek: 1 }}>
          <TooltipProvider>
            <BrowserRouter>
              <AuthProvider>{children}</AuthProvider>
            </BrowserRouter>
            <ConfirmProvider />
            <Toaster />
          </TooltipProvider>
        </DatesProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
}
