import { createColumnHelper, rowPaginationFeature, tableFeatures, type ColumnDef, type RowData } from '@tanstack/react-table';

// Row data is filtered/paginated by the backend, so only the (manual) pagination feature is needed.
export const features = tableFeatures({ rowPaginationFeature });

export type DataColumn<T extends RowData> = ColumnDef<typeof features, T>;

/** Typed column helper: `const col = dataColumns<ObjectRow>(); col.accessor('name', {...})`. */
export function dataColumns<T extends RowData>() {
  return createColumnHelper<typeof features, T>();
}
