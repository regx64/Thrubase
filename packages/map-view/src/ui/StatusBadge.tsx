import type { ReactNode } from 'react';
import { translate } from '../i18n';
import type { Lang, Status } from '../types';
import { Icon, type IconName } from './Icon';

export interface StatusBadgeProps {
  status: Status;
  lang?: Lang;
  children?: ReactNode;
}

export const STATUS_ICON: Record<Status, IconName> = {
  passed: 'check',
  weak: 'warning',
  skipped: 'debug-step-over',
  current: 'location',
  todo: 'chevron-right',
};

/** Icon, word and color always go together. */
export function StatusBadge({ status, lang = 'en', children }: StatusBadgeProps) {
  return (
    <span className={`tb-badge tb-badge-${status}`}>
      <Icon name={STATUS_ICON[status]} />
      {children ?? translate(lang, `status.${status}`)}
    </span>
  );
}
