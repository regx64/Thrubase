import type { ReactNode } from 'react';
import { Icon, type IconName } from './Icon';

export interface EmptyStateProps {
  variant: 'analyzing' | 'no-key' | 'unsupported' | 'error';
  title: string;
  body?: string;
  action?: ReactNode;
}

const ICONS: Record<EmptyStateProps['variant'], IconName> = {
  analyzing: 'loading',
  'no-key': 'key',
  unsupported: 'circle-slash',
  error: 'warning',
};

export function EmptyState({ variant, title, body, action }: EmptyStateProps) {
  return (
    <section
      className={`tb-empty tb-empty-${variant}`}
      role={variant === 'error' ? 'alert' : 'status'}
      aria-live={variant === 'analyzing' ? 'polite' : undefined}
      aria-busy={variant === 'analyzing' ? true : undefined}
    >
      <Icon name={ICONS[variant]} large spin={variant === 'analyzing'} />
      <h2 className="tb-empty-title">{title}</h2>
      {body && <p className="tb-empty-body">{body}</p>}
      {action && <div className="tb-empty-action">{action}</div>}
    </section>
  );
}
