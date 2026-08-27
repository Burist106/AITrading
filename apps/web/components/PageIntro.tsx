import { StatusBadge, type Tone } from "./ui";

export function PageIntro({
  eyebrow,
  title,
  description,
  badge,
  badgeTone = "neutral",
}: {
  eyebrow: string;
  title: string;
  description: string;
  badge?: string;
  badgeTone?: Tone;
}) {
  return (
    <div className="border-line mb-6 flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-3xl">
        <p className="text-gold font-mono text-[0.7rem] tracking-[0.15em] uppercase">
          {eyebrow}
        </p>
        <h1 className="font-display text-ink mt-2 text-2xl font-bold sm:text-3xl">
          {title}
        </h1>
        <p className="text-muted mt-2 text-sm leading-6 sm:text-base">
          {description}
        </p>
      </div>
      {badge ? <StatusBadge tone={badgeTone}>{badge}</StatusBadge> : null}
    </div>
  );
}
