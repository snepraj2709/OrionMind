'use client';

import { Eye, EyeOff } from 'lucide-react';
import { useState } from 'react';

import { AppButton } from '@/components/design-system';
import { cn } from '@/lib/utils';

import { TextInput, type TextInputProps } from './text-input';

export type PasswordInputProps = Omit<TextInputProps, 'type'>;

export function PasswordInput({
  className,
  disabled,
  ...props
}: PasswordInputProps) {
  const [isVisible, setIsVisible] = useState(false);
  const label = isVisible ? 'Hide password' : 'Show password';
  const VisibilityIcon = isVisible ? Eye : EyeOff;

  return (
    <div className="relative">
      <TextInput
        className={cn('pr-12', className)}
        disabled={disabled}
        type={isVisible ? 'text' : 'password'}
        {...props}
      />
      <AppButton
        aria-label={label}
        aria-pressed={isVisible}
        className="text-muted-foreground hover:text-foreground absolute inset-y-0 right-0"
        disabled={disabled}
        onClick={() => setIsVisible((visible) => !visible)}
        type="button"
        variant="icon"
      >
        <VisibilityIcon aria-hidden="true" className="size-5" />
      </AppButton>
    </div>
  );
}
