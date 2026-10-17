import { Component, type ErrorInfo, type ReactNode } from 'react';
import { IconRefresh } from '@tabler/icons-react';
import i18n from '@/i18n';
import { Button } from '@/components/ui/button';
import { isChunkLoadError, reloadForNewBuild } from '@/lib/buildReload';

interface Props {
  children: ReactNode;
  /** A change (e.g. the route) clears a shown error, so the user can go elsewhere without a reload. */
  resetKey?: string;
}

interface State {
  error: unknown;
}

/** Shows a plain message with a reload button instead of a blank page when rendering fails. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error('Page render failed', error, info.componentStack);
    if (isChunkLoadError(error)) reloadForNewBuild();
  }

  componentDidUpdate(previous: Props) {
    if (this.state.error !== null && previous.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (this.state.error === null) return this.props.children;
    return (
      <div role="alert" className="mx-auto my-16 max-w-xl rounded-lg border border-border bg-surface p-6 text-center">
        <h1 className="text-xl font-bold">{i18n.t('common:errorBoundary.title')}</h1>
        <p className="mt-3 text-base text-text-2">{i18n.t('common:errorBoundary.body')}</p>
        <Button className="mt-5 min-h-11" onClick={() => window.location.reload()}>
          <IconRefresh />
          {i18n.t('common:errorBoundary.reload')}
        </Button>
      </div>
    );
  }
}
