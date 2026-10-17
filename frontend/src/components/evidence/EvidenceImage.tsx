import { useEffect, useState, type CSSProperties } from 'react';
import { IconDownload, IconFileOff, IconFileText, IconFileTypePdf, IconPhoto } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useEvidenceContent } from '@/api/hooks/misc';
import type { EvidenceMeta } from '@/api/types';
import { downloadFile, openFile } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Spinner } from '@/components/ui/spinner';
import { useEnum } from '@/i18n/useEnum';
import { cn } from '@/lib/utils';

interface ImageProps {
  id: number;
  alt: string;
  /** thumbnail box size in px; images are fitted with object-fit: cover */
  size?: number;
  /** open a larger preview on click (default true) */
  zoomable?: boolean;
}

/** Evidence PNG/photo. Content is fetched with the Bearer token as a blob (SPEC §8). */
export function EvidenceImage({ id, alt, size = 72, zoomable = true }: ImageProps) {
  const { t } = useTranslation();
  const { data, isPending, isError } = useEvidenceContent(id);
  const [open, setOpen] = useState(false);
  const style: CSSProperties = { width: size, height: size };
  const thumbClass = 'inline-flex flex-none items-center justify-center overflow-hidden rounded bg-surface-sunken text-text-3';

  if (isPending) {
    return (
      <span className={thumbClass} style={style}>
        <Spinner role="presentation" aria-hidden className="size-3.5" />
      </span>
    );
  }
  if (isError) {
    return (
      <span className={thumbClass} style={style} title={t('states.loadError')}>
        <IconFileOff size={18} stroke={1.5} />
      </span>
    );
  }
  return (
    <>
      <button
        type="button"
        className={cn(
          thumbClass,
          'cursor-zoom-in border border-border p-0 transition-shadow hover:border-border-strong hover:shadow-glow focus-visible:ring-1 focus-visible:ring-focus focus-visible:outline-none',
        )}
        style={style}
        onClick={() => zoomable && setOpen(true)}
        aria-label={alt}
      >
        <img src={data.url} alt={alt} className="block size-full object-cover" loading="lazy" />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-fit" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>{alt}</DialogTitle>
          </DialogHeader>
          <img src={data.url} alt={alt} className="block max-h-[75vh] max-w-[min(90vw,1100px)] rounded object-contain" />
        </DialogContent>
      </Dialog>
    </>
  );
}

interface ThumbsProps {
  evidence: EvidenceMeta[];
  size?: number;
}

type RegistryFieldLabel =
  | 'card.registry.fields.name'
  | 'card.registry.fields.address'
  | 'card.registry.fields.city'
  | 'card.registry.fields.region'
  | 'card.registry.fields.cadastralNumber'
  | 'card.registry.fields.authority'
  | 'card.registry.fields.number'
  | 'card.registry.fields.issueDate'
  | 'card.registry.fields.startDate'
  | 'card.registry.fields.commissioningDate'
  | 'card.registry.fields.developer'
  | 'card.registry.fields.bin'
  | 'card.registry.fields.houses'
  | 'card.registry.fields.floors'
  | 'card.registry.fields.comfortClass'
  | 'card.registry.fields.ceilingHeight'
  | 'card.registry.fields.buildingType'
  | 'card.registry.fields.wallFilling'
  | 'card.registry.fields.facadeFinishing'
  | 'card.registry.fields.constructionProgress';

type RegistrySectionTitle =
  | 'card.registry.sections.object'
  | 'card.registry.sections.basis'
  | 'card.registry.sections.developer'
  | 'card.registry.sections.building'
  | 'card.registry.sections.authorized'
  | 'card.registry.sections.supervising'
  | 'card.registry.sections.technicalSupervising';

interface RegistryField {
  label: RegistryFieldLabel;
  value: string;
}

interface RegistrySection {
  title: RegistrySectionTitle;
  fields: RegistryField[];
}

interface RegistryResponseView {
  summary: RegistrySection[];
  additional: RegistrySection[];
}

interface RegistryVersion {
  key: string;
  captures: EvidenceMeta[];
}

type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as JsonRecord) : null;
}

function asText(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return null;
}

function makeField(label: RegistryFieldLabel, value: unknown): RegistryField | null {
  const text = asText(value);
  return text === null ? null : { label, value: text };
}

function nonEmptySection(title: RegistrySectionTitle, fields: Array<RegistryField | null>): RegistrySection | null {
  const available = fields.filter((field): field is RegistryField => field !== null);
  return available.length > 0 ? { title, fields: available } : null;
}

function companySection(
  title: RegistrySectionTitle,
  value: unknown,
): RegistrySection | null {
  const company = asRecord(value);
  return nonEmptySection(title, [
    makeField('card.registry.fields.developer', company?.name ?? value),
    makeField('card.registry.fields.bin', company?.bin),
  ]);
}

/** Reads the saved Homeportal detail envelope without exposing unrecognized payloads as raw JSON. */
function parseRegistryResponse(payload: unknown): RegistryResponseView | null {
  const root = asRecord(payload);
  if (!root) return null;
  const data = asRecord(root.data);
  if (!data) return null;
  const basic = asRecord(data.basicData) ?? {};
  const location = asRecord(data.locationData) ?? {};
  const object = asRecord(data.objectData) ?? {};
  const companies = asRecord(data.companyData) ?? {};
  const authority = asRecord(basic.authority);
  const city = asRecord(basic.city);
  const region = asRecord(basic.region);
  const developer = basic.developerData ?? companies.developerData;

  const summary = [
    nonEmptySection('card.registry.sections.object', [
      makeField('card.registry.fields.name', basic.name),
      makeField('card.registry.fields.address', basic.address),
      makeField('card.registry.fields.city', city?.name_ru),
      makeField('card.registry.fields.region', region?.name_ru),
      makeField('card.registry.fields.cadastralNumber', location.cadastral_number),
    ]),
    nonEmptySection('card.registry.sections.basis', [
      makeField('card.registry.fields.authority', authority?.name),
      makeField('card.registry.fields.number', basic.warranty_number),
      makeField('card.registry.fields.issueDate', basic.issue_date),
      makeField('card.registry.fields.startDate', basic.start_date),
      makeField('card.registry.fields.commissioningDate', basic.commissioning_date),
    ]),
    companySection('card.registry.sections.developer', developer),
  ].filter((section): section is RegistrySection => section !== null);

  const additional = [
    nonEmptySection('card.registry.sections.building', [
      makeField('card.registry.fields.houses', object.no_of_houses),
      makeField('card.registry.fields.floors', object.no_of_floors),
      makeField('card.registry.fields.comfortClass', object.comfort_class),
      makeField('card.registry.fields.ceilingHeight', object.ceiling_height),
      makeField('card.registry.fields.buildingType', object.building_type),
      makeField('card.registry.fields.wallFilling', object.wall_filling),
      makeField('card.registry.fields.facadeFinishing', object.facade_finishing),
      makeField('card.registry.fields.constructionProgress', basic.construction_progress),
    ]),
    companySection('card.registry.sections.authorized', companies.authorizedData),
    companySection('card.registry.sections.supervising', companies.supervisingData),
    companySection('card.registry.sections.technicalSupervising', companies.technicalSupervisingData),
  ].filter((section): section is RegistrySection => section !== null);

  return summary.length > 0 || additional.length > 0 ? { summary, additional } : null;
}

function newestFirst(a: EvidenceMeta, b: EvidenceMeta): number {
  const aTime = Date.parse(a.captured_at);
  const bTime = Date.parse(b.captured_at);
  const aValid = Number.isFinite(aTime);
  const bValid = Number.isFinite(bTime);
  if (aValid && bValid && aTime !== bTime) return bTime - aTime;
  if (aValid !== bValid) return bValid ? 1 : -1;
  return b.id - a.id;
}

function groupRegistryVersions(evidence: EvidenceMeta[]): RegistryVersion[] {
  const grouped = new Map<string, EvidenceMeta[]>();
  for (const item of evidence) {
    const digest = typeof item.sha256 === 'string' ? item.sha256.trim().toLowerCase() : '';
    const key = digest ? `sha:${digest}` : `evidence:${item.id}`;
    grouped.set(key, [...(grouped.get(key) ?? []), item]);
  }
  return Array.from(grouped, ([key, captures]) => ({ key, captures: captures.sort(newestFirst) })).sort((a, b) =>
    newestFirst(a.captures[0], b.captures[0]),
  );
}

function formatCaptureDate(value: string, locale: string): string | null {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function RegistrySectionView({ section }: { section: RegistrySection }) {
  const { t } = useTranslation('objects');
  return (
    <section className="min-w-0 rounded border border-border bg-surface px-3 py-2">
      <h3 className="mb-2 text-2xs font-bold tracking-wider text-text-2 uppercase">{t(section.title)}</h3>
      <dl className="grid min-w-0 gap-x-3 gap-y-2 sm:grid-cols-2">
        {section.fields.map((field) => (
          <div key={field.label} className="min-w-0">
            <dt className="text-xs text-text-3">{t(field.label)}</dt>
            <dd className="break-words text-sm text-text">{field.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function RegistryResponseDialog({
  evidence,
  versions,
  selectedVersionKey,
  onSelectVersion,
  onOpenChange,
}: {
  evidence: EvidenceMeta;
  versions: RegistryVersion[];
  selectedVersionKey: string;
  onSelectVersion: (key: string) => void;
  onOpenChange: (open: boolean) => void;
}) {
  const { t, i18n } = useTranslation('objects');
  const { data, isPending, isError, refetch } = useEvidenceContent(evidence.id);
  const [parseState, setParseState] = useState<'reading' | 'ready' | 'unsupported' | 'malformed'>('reading');
  const [view, setView] = useState<RegistryResponseView | null>(null);
  const [downloadState, setDownloadState] = useState<'idle' | 'loading' | 'error'>('idle');

  useEffect(() => {
    let active = true;
    if (!data?.blob) return () => { active = false; };

    void data.blob.text().then(
      (content) => {
        if (!active) return;
        try {
          const parsed = parseRegistryResponse(JSON.parse(content));
          if (parsed) {
            setView(parsed);
            setParseState('ready');
          } else {
            setParseState('unsupported');
          }
        } catch {
          setParseState('malformed');
        }
      },
      () => {
        if (active) setParseState('malformed');
      },
    );
    return () => {
      active = false;
    };
  }, [data?.blob]);

  const download = async () => {
    setDownloadState('loading');
    try {
      await downloadFile(`/evidence/${evidence.id}/content`, `registry-response-${evidence.id}.json`);
      setDownloadState('idle');
    } catch {
      setDownloadState('error');
    }
  };

  const locale = i18n.resolvedLanguage ?? i18n.language;
  const capturedAt = formatCaptureDate(evidence.captured_at, locale) ?? t('card.registry.unknownDate');
  const selectedVersion = versions.find((version) => version.key === selectedVersionKey) ?? versions[0];
  const isLatestVersion = selectedVersion === versions[0];

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('card.registry.title')}</DialogTitle>
          <DialogDescription>
            {t(isLatestVersion ? 'card.registry.currentVersion' : 'card.registry.capturedAt', { date: capturedAt })} · #{evidence.id}
          </DialogDescription>
        </DialogHeader>

        {versions.length > 1 && selectedVersion && (
          <div className="min-w-0">
            <label htmlFor={`registry-version-${evidence.id}`} className="mb-1 block text-xs text-text-2">
              {t('card.registry.versionSelect')}
            </label>
            <select
              id={`registry-version-${evidence.id}`}
              className="min-h-11 w-full rounded border border-border-strong bg-surface-sunken px-2 text-sm text-text focus-visible:ring-1 focus-visible:ring-focus focus-visible:outline-none"
              value={selectedVersion.key}
              onChange={(event) => onSelectVersion(event.currentTarget.value)}
            >
              {versions.map((version, index) => {
                const latest = version.captures[0];
                const date = formatCaptureDate(latest.captured_at, locale) ?? t('card.registry.unknownDate');
                return (
                  <option key={version.key} value={version.key}>
                    {index === 0
                      ? t('card.registry.latestVersion', { date, id: latest.id })
                      : t('card.registry.olderVersion', { date, id: latest.id })}
                  </option>
                );
              })}
            </select>
          </div>
        )}

        <div className="min-w-0 space-y-3">
          {isPending && (
            <div className="flex items-center gap-2 py-3 text-sm text-text-2" role="status">
              <Spinner aria-hidden className="size-4" />
              {t('card.registry.loading')}
            </div>
          )}
          {isError && (
            <div className="rounded border border-border bg-surface px-3 py-3" role="alert">
              <p className="text-sm text-text">{t('card.registry.loadError')}</p>
              <Button variant="outline" className="mt-2 min-h-11" onClick={() => void refetch()}>
                {t('card.registry.retry')}
              </Button>
            </div>
          )}
          {!isPending && !isError && parseState === 'reading' && (
            <div className="py-3 text-sm text-text-2" role="status">{t('card.registry.reading')}</div>
          )}
          {!isPending && !isError && parseState === 'malformed' && (
            <p className="rounded border border-border bg-surface px-3 py-3 text-sm text-text-2" role="status">
              {t('card.registry.malformed')}
            </p>
          )}
          {!isPending && !isError && parseState === 'unsupported' && (
            <p className="rounded border border-border bg-surface px-3 py-3 text-sm text-text-2" role="status">
              {t('card.registry.unsupported')}
            </p>
          )}
          {!isPending && !isError && parseState === 'ready' && view && (
            <>
              {view.summary.length > 0 && (
                <div className="grid min-w-0 gap-2 sm:grid-cols-2">
                  {view.summary.map((section) => <RegistrySectionView key={section.title} section={section} />)}
                </div>
              )}
              {view.additional.length > 0 && (
                <details className="rounded border border-border bg-surface px-3 py-2">
                  <summary className="min-h-11 cursor-pointer content-center text-sm font-medium text-text">
                    {t('card.registry.additional')}
                  </summary>
                  <div className="grid min-w-0 gap-2 pt-2 sm:grid-cols-2">
                    {view.additional.map((section) => <RegistrySectionView key={section.title} section={section} />)}
                  </div>
                </details>
              )}
            </>
          )}

          {versions.length > 0 && versions.reduce((count, version) => count + version.captures.length, 0) > 1 && (
            <details className="rounded border border-border bg-surface px-3 py-2">
              <summary className="min-h-11 cursor-pointer content-center text-sm font-medium text-text">
                {t('card.registry.history', { count: versions.reduce((total, version) => total + version.captures.length, 0) })}
              </summary>
              <ul className="space-y-3 pt-2 text-xs text-text-2">
                {versions.map((version, index) => {
                  const latest = version.captures[0];
                  const date = formatCaptureDate(latest.captured_at, locale) ?? t('card.registry.unknownDate');
                  return (
                    <li key={version.key} className="break-words">
                      {versions.length > 1 && (
                        <p className="mb-1 font-medium text-text">
                          {index === 0
                            ? t('card.registry.latestVersion', { date, id: latest.id })
                            : t('card.registry.olderVersion', { date, id: latest.id })}
                        </p>
                      )}
                      <ul className="space-y-1">
                        {version.captures.map((capture) => {
                          const capturedAt = formatCaptureDate(capture.captured_at, locale) ?? t('card.registry.unknownDate');
                          return <li key={capture.id}>{capturedAt} · #{capture.id}</li>;
                        })}
                      </ul>
                    </li>
                  );
                })}
              </ul>
            </details>
          )}
        </div>

        <DialogFooter className="items-stretch sm:items-end">
          {downloadState === 'error' && <p className="text-sm text-zone-red-ink" role="alert">{t('card.registry.downloadError')}</p>}
          <Button
            variant="outline"
            className="min-h-11 max-w-full whitespace-normal"
            loading={downloadState === 'loading'}
            onClick={() => void download()}
          >
            <IconDownload />
            {t('card.registry.download')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RegistryResponseEntry({ evidence }: { evidence: EvidenceMeta[] }) {
  const { t } = useTranslation('objects');
  const versions = groupRegistryVersions(evidence);
  const [open, setOpen] = useState(false);
  const [selectedVersionKey, setSelectedVersionKey] = useState(versions[0]?.key ?? '');
  const latestVersion = versions[0];
  const currentVersion = versions.find((version) => version.key === selectedVersionKey) ?? latestVersion;
  const currentEvidence = currentVersion?.captures[0];
  if (!latestVersion || !currentVersion || !currentEvidence) return null;

  const summary = versions.length > 1
    ? t('card.registry.versions', { count: versions.length })
    : currentVersion.captures.length > 1
      ? t('card.registry.identicalCount', { count: currentVersion.captures.length })
      : null;
  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) setSelectedVersionKey(latestVersion.key);
    setOpen(nextOpen);
  };

  return (
    <>
      <button
        type="button"
        className="inline-flex min-h-11 max-w-full items-center gap-1.5 rounded border border-border-strong bg-surface-raised px-2.5 py-1.5 text-left text-sm text-text hover:bg-hover focus-visible:ring-1 focus-visible:ring-focus focus-visible:outline-none"
        onClick={() => {
          setSelectedVersionKey(latestVersion.key);
          setOpen(true);
        }}
        aria-label={t('card.registry.open')}
      >
        <IconFileText size={16} className="flex-none" />
        <span>{t('card.registry.title')}</span>
        {summary && <span className="text-xs text-text-3">{summary}</span>}
      </button>
      {open && (
        <RegistryResponseDialog
          key={currentEvidence.id}
          evidence={currentEvidence}
          versions={versions}
          selectedVersionKey={currentVersion.key}
          onSelectVersion={setSelectedVersionKey}
          onOpenChange={handleOpenChange}
        />
      )}
    </>
  );
}

/** Row of evidence previews: images inline, registry responses readable, other kinds as downloads. */
export function EvidenceThumbs({ evidence, size = 72 }: ThumbsProps) {
  const e = useEnum();
  const registryResponses = evidence.filter((item) => item.kind === 'registry_response');
  return (
    <div className="flex flex-wrap gap-2">
      {evidence.filter((item) => item.kind !== 'registry_response').map((item) =>
        item.content_type.startsWith('image/') ? (
          <EvidenceImage key={item.id} id={item.id} alt={`${e('evidence_kind', item.kind)} #${item.id}`} size={size} />
        ) : (
          <button
            key={item.id}
            type="button"
            className="inline-flex items-center gap-1.5 rounded border border-border-strong bg-surface-raised px-2.5 py-1.5 text-sm text-text hover:bg-hover focus-visible:ring-1 focus-visible:ring-focus focus-visible:outline-none"
            onClick={() => void openFile(`/evidence/${item.id}/content`)}
          >
            {item.content_type === 'application/pdf' ? <IconFileTypePdf size={16} /> : <IconPhoto size={16} />}
            {e('evidence_kind', item.kind)}
          </button>
        ),
      )}
      {registryResponses.length > 0 && <RegistryResponseEntry evidence={registryResponses} />}
    </div>
  );
}
