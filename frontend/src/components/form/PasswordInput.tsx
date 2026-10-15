import { useState, type ComponentProps } from 'react';
import { IconEye, IconEyeOff } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { InputWrapper } from '@/components/form/InputWrapper';
import { useFieldControl, type FieldProps } from '@/components/form/useFieldControl';
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group';

type PasswordInputProps = FieldProps & Omit<ComponentProps<'input'>, keyof FieldProps | 'type' | 'children'>;

/** Password field with a show/hide button (replaces the Mantine `PasswordInput`). */
export function PasswordInput({ id, label, description, error, required, className, ...props }: PasswordInputProps) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  const field = useFieldControl({ id, description, error, required });
  return (
    <InputWrapper field={field} label={label} description={description} error={error} required={required} className={className}>
      <InputGroup>
        <InputGroupInput {...field.controlProps} {...props} type={visible ? 'text' : 'password'} />
        <InputGroupAddon align="inline-end">
          <InputGroupButton aria-label={visible ? t('ui.hidePassword') : t('ui.showPassword')} aria-pressed={visible} onClick={() => setVisible((current) => !current)}>
            {visible ? <IconEyeOff /> : <IconEye />}
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
    </InputWrapper>
  );
}
