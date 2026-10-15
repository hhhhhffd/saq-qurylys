import { useRiskFactors } from '@/api/hooks/reference';
import { useEnum } from '@/i18n/useEnum';

/** Factor name and description: translated by code, falling back to the text stored on the backend. */
export function useFactorLabels() {
  const e = useEnum();
  const { data: factors } = useRiskFactors();
  const storedDescription = (code: string) => factors?.find((factor) => factor.code === code)?.description;

  return {
    name: (code: string): string => {
      const label = e('risk_factor', code);
      return label === code ? (storedDescription(code) ?? code) : label;
    },
    description: (code: string): string => {
      const label = e('risk_factor_desc', code);
      return label === code ? (storedDescription(code) ?? '') : label;
    },
  };
}
