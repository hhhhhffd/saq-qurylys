import { useMemo, useState } from 'react';
import { Select, type SelectProps } from '@mantine/core';
import { useDebouncedValue } from '@/lib/hooks';
import { useObject, useObjects } from '@/api/hooks/objects';

interface Props extends Omit<SelectProps, 'data' | 'value' | 'onChange' | 'searchable' | 'onSearchChange'> {
  value: number | null;
  onChange: (id: number | null) => void;
}

/** Searchable object picker backed by `GET /objects?q=`. */
export function ObjectSelect({ value, onChange, ...rest }: Props) {
  const [search, setSearch] = useState('');
  const [debounced] = useDebouncedValue(search, 250);
  const { data } = useObjects({ q: debounced || undefined, limit: 20 });

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
    <Select
      {...rest}
      data={merged}
      value={value != null ? String(value) : null}
      searchable
      clearable
      filter={({ options: all }) => all}
      onSearchChange={setSearch}
      onChange={(next) => onChange(next ? Number(next) : null)}
    />
  );
}
