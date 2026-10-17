import { IconArrowRight, IconFilePlus, IconRefresh } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { useCreateSignal, useSignals } from '@/api/hooks/signals';
import { readBreakdown, type ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { useEnum } from '@/i18n/useEnum';

export function ObjectReviewActions({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const { canEditRegistry, canManageSignals } = useAuth();
  const navigate = useNavigate();
  const createSignal = useCreateSignal();

  const confirmationQuery = useSignals({ object_id: object.id, status: 'requires_confirmation', limit: 1 });
  const returnedQuery = useSignals({ object_id: object.id, status: 'returned', limit: 1 });
  const sentQuery = useSignals({ object_id: object.id, status: 'sent', limit: 1 });
  const respondedQuery = useSignals({ object_id: object.id, status: 'responded', limit: 1 });
  const queries = [confirmationQuery, returnedQuery, sentQuery, respondedQuery];
  const latestScore = object.latest_score;
  const breakdown = readBreakdown(latestScore);
  const hasUnresolvedChecks =
    latestScore !== null && (!breakdown || breakdown.needs_check.length > 0 || breakdown.legal_basis_status === 'unknown');
  const assessment = !latestScore ? 'unscored' : hasUnresolvedChecks ? 'needsCheck' : latestScore.zone;
  const guidanceKey =
    !canEditRegistry && (assessment === 'unscored' || assessment === 'needsCheck')
      ? `${assessment}Readonly`
      : assessment;
  const reviewTarget = assessment === 'yellow' || assessment === 'red' ? '#risk' : '#documents';
  const reviewLabel = assessment === 'yellow' || assessment === 'red' ? 'reviewRisk' : 'checkDocuments';
  const foundSignals = queries
    .flatMap((query) => query.data?.items ?? [])
    .filter((signal) => signal.object_id === object.id && signal.status !== 'closed')
    .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id);
  const activeSignal = foundSignals[0];
  const checkingSignals = queries.some((query) => query.isPending || query.isFetching);
  const failedLookup = queries.some((query) => query.isError);

  const create = () =>
    createSignal.mutate(object.id, {
      onSuccess: (signal) => void navigate(`/signals/${signal.id}`),
      onError: () => queries.forEach((query) => void query.refetch()),
    });

  return (
    <Panel title={t('card.nextStep.title')} id="next-step">
      {activeSignal ? (
        <>
          <p className="text-sm text-text-2">{t('card.nextStep.openExists', { number: activeSignal.number })}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Chip>{e('signal_status', activeSignal.status)}</Chip>
            <Button asChild className="min-h-11">
              <Link to={`/signals/${activeSignal.id}`}>
                {t('card.nextStep.open')}
                <IconArrowRight />
              </Link>
            </Button>
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-text-2">{t(`card.nextStep.guidance.${guidanceKey}`)}</p>
          {failedLookup ? (
            <div className="mt-3">
              <p role="alert" className="text-sm text-text-2">
                {t('card.nextStep.lookupFailed')}
              </p>
              <Button
                className="mt-2 min-h-11"
                variant="secondary"
                loading={checkingSignals}
                onClick={() => queries.forEach((query) => void query.refetch())}
              >
                <IconRefresh />
                {t('card.nextStep.retry')}
              </Button>
            </div>
          ) : checkingSignals ? (
            <p role="status" aria-live="polite" className="mt-3 text-sm text-text-2">
              {t('card.nextStep.checking')}
            </p>
          ) : (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {assessment !== 'green' && (
                <Button asChild className="min-h-11">
                  <a href={reviewTarget}>{t(`card.nextStep.${reviewLabel}`)}</a>
                </Button>
              )}
              {canManageSignals && (
                <Button className="min-h-11" variant="secondary" loading={createSignal.isPending} onClick={create}>
                  <IconFilePlus />
                  {t('card.nextStep.create')}
                </Button>
              )}
              {!canManageSignals && assessment !== 'green' && (
                <p className="text-sm text-text-3">{t('card.nextStep.noPermission')}</p>
              )}
            </div>
          )}
        </>
      )}

      <Link
        to={`/signals?object_id=${object.id}`}
        className="mt-3 inline-flex min-h-11 items-center text-sm text-text-2 underline-offset-4 hover:text-text hover:underline focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        {t('card.nextStep.all')}
      </Link>
    </Panel>
  );
}
