import { useMemo, useState } from 'react';
import { useObject, useObjects } from '@/api/hooks/objects';
import { SelectInput } from '@/components/form/SelectInput';
import type { FieldProps } from '@/components/form/useFieldControl';
import { useDebouncedValue } from '@/lib/hooks';

interface Props extends FieldProps {
  value: number | null;
  onChange: (id: number | null) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Mantine leftover of callers that are not migrated yet; ignored. Remove with the last caller. */
  comboboxProps?: unknown;
}

/** Searchable object picker backed by `GET /objects?q=`. */
export function ObjectSelect({ value, onChange, comboboxProps: _ignored, ...rest }: Props) {
  const [search, setSearch] = useState('');
  const [debounced] = useDebouncedValue(search, 250);
  const { data, isFetching } = useObjects({ q: debounced || undefined, limit: 20 });

  const options = useMemo(
    () => (data?.items ?? []).map((item) => ({ value: String(item.id), label: `${item.code} · ${item.name}` })),
    [data],
  );
  // The selected object may not be in the current search results (e.g. restored from the URL).
  const known = options.some((option) => option.value === String(value));
  const selected = useObject(value ?? 0, value != null && !known);
  const merged = useMemo(
    () =>
      selected.data && !known
        ? [...options, { value: String(selected.data.id), label: `${selected.data.code} · ${selected.data.name}` }]
        : options,
    [options, selected.data, known],
  );

  return (
    <SelectInput
      {...rest}
      data={merged}
      value={value != null ? String(value) : null}
      clearable
      loading={isFetching}
      onSearchChange={setSearch}
      onChange={(next) => onChange(next ? Number(next) : null)}
    />
  );
}
