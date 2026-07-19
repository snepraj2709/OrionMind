import type { ReactNode } from 'react';

import { InlineError } from '@/components/feedback';

export interface FormErrorProps {
  children: ReactNode;
}

export function FormError({ children }: FormErrorProps) {
  return <InlineError>{children}</InlineError>;
}
