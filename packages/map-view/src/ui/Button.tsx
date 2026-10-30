import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { Icon, type IconProps } from './Icon';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md';
  icon?: IconProps['name'];
}

/** secondary is the default; primary appears once per screen; ghost only for reversible actions. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', icon, className, children, type, ...rest },
  ref,
) {
  const classes = ['tb-button', `tb-button-${variant}`, `tb-button-${size}`];
  if (className) classes.push(className);
  return (
    <button ref={ref} type={type ?? 'button'} className={classes.join(' ')} {...rest}>
      {icon && <Icon name={icon} />}
      {children}
    </button>
  );
});
