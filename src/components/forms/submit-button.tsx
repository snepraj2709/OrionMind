import type { AppButtonProps } from '@/components/design-system';
import { AppButton } from '@/components/design-system';

export interface SubmitButtonProps extends Omit<AppButtonProps, 'type'> {
  loading?: boolean;
}

export function SubmitButton(props: SubmitButtonProps) {
  return <AppButton type="submit" {...props} />;
}
