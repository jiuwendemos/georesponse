import { cloneElement, isValidElement, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react'
import { cx } from '../lib/format'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

export function Button({
  variant = 'secondary',
  size = 'md',
  loading,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean }) {
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={cx(
        'btn',
        variant === 'primary' && 'btn-primary',
        variant === 'ghost' && 'btn-ghost',
        variant === 'danger' && 'btn-danger',
        size === 'sm' && 'btn-sm',
        size === 'lg' && 'btn-lg',
        loading && 'is-loading',
        className,
      )}
      aria-busy={loading || undefined}
    >
      {loading && <span className="ds-spinner" aria-hidden />}
      {children}
    </button>
  )
}

export function IconButton({
  label,
  children,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return (
    <button {...props} className={cx('icon-btn', className)} aria-label={label} title={label}>
      {children}
    </button>
  )
}

export function Badge({ tone = 'neutral', children, className }: { tone?: 'neutral' | 'info' | 'success' | 'warn' | 'danger'; children: ReactNode; className?: string }) {
  return <span className={cx('ds-badge', `ds-badge-${tone}`, className)}>{children}</span>
}

export function Card({ title, eyebrow, actions, children, className }: { title?: string; eyebrow?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx('ds-card', className)}>
      {(title || eyebrow || actions) && (
        <header className="ds-card-head">
          <div>
            {eyebrow && <span className="eyebrow">{eyebrow}</span>}
            {title && <h3>{title}</h3>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function Field({
  label,
  hint,
  error,
  children,
  id,
}: {
  label: string
  hint?: string
  error?: string
  children: ReactNode
  id?: string
}) {
  // A <label> around a radiogroup would steal every radio's accessible name.
  // Associate only real inputs; give groups their own labelled control.
  const labelledChild =
    !id && isValidElement<{ 'aria-label'?: string }>(children) && children.type === TextInput && !children.props['aria-label']
      ? cloneElement(children, { 'aria-label': label })
      : children
  return (
    <div className={cx('ds-field', error && 'has-error')}>
      {id ? <label className="ds-field-label" htmlFor={id}>{label}</label> : <span className="ds-field-label">{label}</span>}
      {labelledChild}
      {error ? <span className="ds-field-error" role="alert">{error}</span> : hint ? <span className="ds-field-hint">{hint}</span> : null}
    </div>
  )
}

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx('ds-input', className)} />
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div className="ds-segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          className={cx('ds-segment', value === option.value && 'active')}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function EmptyState({ icon, title, body, action }: { icon?: ReactNode; title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="ds-empty">
      {icon && <div className="ds-empty-icon">{icon}</div>}
      <b>{title}</b>
      {body && <span>{body}</span>}
      {action}
    </div>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <span className="ds-spinner" role="status" aria-label={label} />
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="ds-kbd">{children}</kbd>
}
