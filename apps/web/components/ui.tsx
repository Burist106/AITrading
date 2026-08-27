import type { ReactNode } from "react";

const toneStyles = {
  neutral: "border-line text-muted bg-elevated",
  success: "border-buy/40 text-buy bg-buy/8",
  warning: "border-warning/40 text-warning bg-warning/8",
  negative: "border-sell/50 text-sell bg-sell/8",
  blocked: "border-blocked/50 text-blocked bg-blocked/8",
  critical: "border-critical/60 text-critical bg-critical/10",
  info: "border-info/40 text-info bg-info/8",
  gold: "border-gold/40 text-gold bg-gold/8",
} as const;

export type Tone = keyof typeof toneStyles;

export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: Tone;
}) {
  return (
    <span
      className={`inline-flex min-h-7 items-center border px-2.5 py-1 font-mono text-[0.7rem] font-medium uppercase ${toneStyles[tone]}`}
    >
      {children}
    </span>
  );
}

export function Card({
  children,
  className = "",
  labelledBy,
}: {
  children: ReactNode;
  className?: string;
  labelledBy?: string;
}) {
  return (
    <section
      aria-labelledby={labelledBy}
      className={`border-line bg-surface border p-4 shadow-[0_20px_70px_rgb(0_0_0/0.12)] sm:p-5 ${className}`}
    >
      {children}
    </section>
  );
}

export function SectionHeading({
  id,
  eyebrow,
  title,
  aside,
}: {
  id?: string;
  eyebrow?: string;
  title: string;
  aside?: ReactNode;
}) {
  return (
    <div className="border-line mb-4 flex flex-wrap items-start justify-between gap-3 border-b pb-3">
      <div>
        {eyebrow ? (
          <p className="text-gold mb-1 font-mono text-[0.7rem] tracking-[0.12em] uppercase">
            {eyebrow}
          </p>
        ) : null}
        <h2
          id={id}
          className="font-display text-ink text-base font-bold sm:text-lg"
        >
          {title}
        </h2>
      </div>
      {aside}
    </div>
  );
}

export function Metric({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: Tone;
}) {
  const valueTone =
    tone === "neutral" ? "text-ink" : toneStyles[tone].split(" ")[1];
  return (
    <div className="border-line min-w-0 border-l pl-3">
      <dt className="text-muted text-xs leading-5">{label}</dt>
      <dd
        className={`mt-1 truncate font-mono text-base font-medium ${valueTone}`}
      >
        {value}
      </dd>
      {detail ? (
        <dd className="text-muted mt-1 text-xs leading-5">{detail}</dd>
      ) : null}
    </div>
  );
}

export function DefinitionRow({
  label,
  value,
  emphasized = false,
}: {
  label: string;
  value: ReactNode;
  emphasized?: boolean;
}) {
  return (
    <div className="border-line/70 grid min-h-11 grid-cols-[minmax(0,1fr)_auto] items-center gap-4 border-b py-2.5 last:border-b-0">
      <dt className="text-muted text-sm">{label}</dt>
      <dd
        className={`text-right font-mono text-sm ${emphasized ? "text-ink font-semibold" : "text-muted"}`}
      >
        {value}
      </dd>
    </div>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="border-line flex min-h-44 flex-col items-center justify-center border border-dashed px-5 py-8 text-center">
      <span aria-hidden="true" className="bg-line-strong mb-3 block size-2" />
      <h3 className="font-display text-ink text-base font-bold">{title}</h3>
      <p className="text-muted mt-2 max-w-md text-sm leading-6">
        {description}
      </p>
    </div>
  );
}
