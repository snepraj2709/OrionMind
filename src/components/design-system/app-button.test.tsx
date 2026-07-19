import { render, screen } from '@testing-library/react';
import { Check } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import { AppButton, type AppButtonVariant } from './app-button';

describe('AppButton', () => {
  it.each<AppButtonVariant>([
    'primary',
    'secondary',
    'ghost',
    'destructive',
    'link',
    'icon',
  ])('renders the %s variant through the shared implementation', (variant) => {
    render(
      <AppButton
        aria-label={variant === 'icon' ? 'Icon action' : undefined}
        variant={variant}
      >
        {variant === 'icon' ? <Check aria-hidden="true" /> : variant}
      </AppButton>,
    );

    expect(screen.getByRole('button')).toHaveAttribute('data-slot', 'button');
  });

  it('exposes loading and disabled state without removing the button label', () => {
    render(
      <AppButton loading loadingLabel="Saving entry">
        Save
      </AppButton>,
    );

    const button = screen.getByRole('button', { name: 'Saving entry' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
  });

  it('supports left and right icons', () => {
    render(
      <AppButton
        leftIcon={<Check data-testid="left-icon" />}
        rightIcon={<Check data-testid="right-icon" />}
      >
        Continue
      </AppButton>,
    );

    expect(screen.getByTestId('left-icon')).toBeInTheDocument();
    expect(screen.getByTestId('right-icon')).toBeInTheDocument();
  });

  it('applies the approved pill shape without changing button behavior', () => {
    render(
      <AppButton shape="pill" variant="secondary">
        This resonates
      </AppButton>,
    );

    expect(screen.getByRole('button', { name: 'This resonates' })).toHaveClass(
      'radius-pill',
      'control-default',
    );
  });
});
