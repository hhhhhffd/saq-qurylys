import { Button, Group, NumberInput } from '@mantine/core';
import { DateInput, type DateInputProps } from '@mantine/dates';
import type { GetInputPropsReturnType } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { DISPLAY_DATE_FORMAT, parseDateInput } from './utils';

/** `DateInput` that shows and accepts `DD.MM.YYYY` and stores `YYYY-MM-DD`. */
export function DateField(props: DateInputProps) {
  const { t } = useTranslation('objectForms');
  return (
    <DateInput
      valueFormat={DISPLAY_DATE_FORMAT}
      dateParser={parseDateInput}
      placeholder={t('datePlaceholder')}
      {...props}
    />
  );
}

interface CoordinateFieldsProps {
  latProps: GetInputPropsReturnType;
  lonProps: GetInputPropsReturnType;
}

/** Latitude and longitude as two grid cells; pair them with `coordinateRule` in the form's validation. */
export function CoordinateFields({ latProps, lonProps }: CoordinateFieldsProps) {
  const { t } = useTranslation('objectForms');
  return (
    <>
      <NumberInput label={t('lat')} placeholder="51.128200" decimalScale={6} hideControls {...latProps} />
      <NumberInput label={t('lon')} placeholder="71.430400" decimalScale={6} hideControls {...lonProps} />
    </>
  );
}

interface FormFooterProps {
  loading: boolean;
  onCancel: () => void;
  submitLabel: string;
  submitDisabled?: boolean;
}

/** Cancel and submit, aligned right. The submit button belongs to the surrounding `<form>`. */
export function FormFooter({ loading, onCancel, submitLabel, submitDisabled }: FormFooterProps) {
  const { t } = useTranslation();
  return (
    <Group justify="flex-end" mt="lg">
      <Button variant="default" onClick={onCancel} disabled={loading}>
        {t('cancel')}
      </Button>
      <Button type="submit" loading={loading} disabled={submitDisabled}>
        {submitLabel}
      </Button>
    </Group>
  );
}
