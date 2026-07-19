'use client';

import { Component, type ErrorInfo, type ReactNode } from 'react';

import { AppButton } from '@/components/design-system';

import { PageErrorState } from './states';

export interface AppErrorBoundaryProps {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface AppErrorBoundaryState {
  error?: Error;
}

export class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = {};

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  reset = () => {
    this.setState({ error: undefined });
  };

  render() {
    const { children, fallback } = this.props;
    const { error } = this.state;

    if (!error) return children;

    if (fallback) return fallback(error, this.reset);

    return (
      <PageErrorState
        action={<AppButton onClick={this.reset}>Try again</AppButton>}
        description="This part of Orion could not be displayed."
      />
    );
  }
}
