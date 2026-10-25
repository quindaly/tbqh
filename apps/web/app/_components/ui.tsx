import type { ButtonHTMLAttributes, ReactNode } from "react";

/** Small building blocks for the Paper and Night look, so pages stay consistent. */

export function Heading({ children, size = 34 }: { children: ReactNode; size?: 34 | 28 | 44 }) {
  const cls =
    size === 44
      ? "text-[44px] leading-[1.05]"
      : size === 28
      ? "text-[28px] leading-[1.15]"
      : "text-[34px] leading-[1.1]";
  return <h1 className={`font-serif ${cls} tracking-[-0.01em] font-normal`}>{children}</h1>;
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <span className="text-xs tracking-[0.14em] uppercase text-muted">{children}</span>;
}

export function PrimaryButton(props: ButtonHTMLAttributes<HTMLButtonElement>) {
  const { className = "", ...rest } = props;
  return (
    <button
      {...rest}
      className={`w-full px-6 bg-btn text-btn-text rounded-md hover:opacity-90 transition disabled:opacity-50 min-h-[56px] text-[17px] font-medium ${className}`}
    />
  );
}

export function SecondaryButton(props: ButtonHTMLAttributes<HTMLButtonElement>) {
  const { className = "", ...rest } = props;
  return (
    <button
      {...rest}
      className={`w-full px-6 border border-line rounded-md hover:bg-soft transition disabled:opacity-50 min-h-[56px] text-[17px] ${className}`}
    />
  );
}

export function BackLink({ onClick, children = "← Back" }: { onClick: () => void; children?: ReactNode }) {
  return (
    <button onClick={onClick} className="text-sm text-muted hover:underline self-start">
      {children}
    </button>
  );
}
