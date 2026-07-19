import { useId } from "react";

/**
 * Orbital brand mark: a paper plane (ship your app) with stream
 * trails. Original artwork - intentionally distinct from Streamlit's kite.
 *
 * variant "mark": gradient glyph on transparent background (app bar, inline)
 * variant "tile": rounded-square app-icon rendering (sign-in, empty states)
 */
export default function Logo({
  size = 24,
  variant = "mark",
}: {
  size?: number;
  variant?: "mark" | "tile";
}) {
  const id = useId();
  const grad = `sh-logo-${id}`;
  const tile = variant === "tile";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="Orbital"
    >
      <defs>
        <linearGradient id={grad} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ff7060" />
          <stop offset="1" stopColor="#c22718" />
        </linearGradient>
      </defs>
      {tile && <rect width="64" height="64" rx="14" fill={`url(#${grad})`} />}
      <g fill={tile ? "#ffffff" : `url(#${grad})`}>
        <path d="M53 13 L15 31 L31 37 Z" opacity={tile ? 0.96 : 1} />
        <path d="M53 13 L31 37 L38 51 Z" opacity={0.72} />
      </g>
      <g
        stroke={tile ? "#ffffff" : `url(#${grad})`}
        strokeWidth="3.2"
        fill="none"
        strokeLinecap="round"
      >
        <path d="M9 42 C 15 38.5, 21 39, 26.5 42.5" opacity="0.9" />
        <path d="M8 50 C 15.5 45.5, 23 46, 29.5 50.5" opacity="0.55" />
      </g>
    </svg>
  );
}
