import './StatusChip.css'

export type ChipVariant = 'demo' | 'synthetic' | 'rule-based' | 'live' | 'info' | 'warn' | 'critical'

interface StatusChipProps {
  variant: ChipVariant
  label?: string
}

const DEFAULTS: Record<ChipVariant, string> = {
  'demo':       'Demo data',
  'synthetic':  'Synthetic',
  'rule-based': 'Rule-based',
  'live':       'Live',
  'info':       'Info',
  'warn':       'Warning',
  'critical':   'Critical',
}

export function StatusChip({ variant, label }: StatusChipProps): JSX.Element {
  const text = label ?? DEFAULTS[variant]
  return (
    <span className={`status-chip status-chip-${variant}`} aria-label={text}>
      {text}
    </span>
  )
}
