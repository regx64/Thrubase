export type IconName =
  | 'check' | 'warning' | 'debug-step-over' | 'location' | 'git-compare' | 'key' | 'file-code' | 'loading'
  | 'circle-slash' | 'info' | 'lightbulb' | 'arrow-right' | 'close' | 'chevron-right' | 'eye' | 'debug-start';

export interface IconProps {
  name: IconName;
  spin?: boolean;
  className?: string;
  /** 16px by default; 24px only in empty states */
  large?: boolean;
  label?: string;
}

/** Codicons as is, so the web and VS Code show identical icons. Decorative unless labelled. */
export function Icon({ name, spin, className, large, label }: IconProps) {
  const classes = ['tb-icon', `tb-icon-${name}`, 'codicon', `codicon-${name}`];
  if (spin) classes.push('tb-icon-spin');
  if (large) classes.push('tb-icon-lg');
  if (className) classes.push(className);
  return label ? (
    <i className={classes.join(' ')} role="img" aria-label={label} />
  ) : (
    <i className={classes.join(' ')} aria-hidden="true" />
  );
}
