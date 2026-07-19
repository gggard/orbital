import { useId } from "react";

/**
 * Orbital brand mark: a satellite tracing an elliptical ring around a
 * central body. Original artwork.
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
  const grad = `orbital-logo-${id}`;
  const tile = variant === "tile";
  const fill = tile ? "#ffffff" : `url(#${grad})`;
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
      {/* central body */}
      <circle cx="32" cy="31" r="7" fill={fill} opacity={tile ? 0.96 : 1} />
      {/* orbit ring */}
      <ellipse
        cx="32"
        cy="31"
        rx="24"
        ry="10"
        transform="rotate(-18 32 31)"
        fill="none"
        stroke={fill}
        strokeWidth="3"
        opacity="0.85"
      />
      {/* satellite */}
      <circle cx="56" cy="31" r="4.5" transform="rotate(-18 32 31)" fill={fill} />
    </svg>
  );
}
