import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 18, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    ...props,
  };
}

export function PixelMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" shapeRendering="crispEdges" aria-hidden="true">
      <rect width="32" height="32" rx="5" fill="currentColor" opacity="0.12" />
      <path
        fill="currentColor"
        d="M6 6h8v4H6zM18 6h8v4h-8zM6 12h4v8H6zM22 12h4v8h-4zM6 22h8v4H6zM18 22h8v4h-8zM12 12h8v8h-8z"
      />
      <path fill="#59e3ff" d="M12 12h4v4h-4zM18 18h2v2h-2z" />
    </svg>
  );
}

export function SparkIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 3l1.6 5.1L19 10l-5.4 1.9L12 17l-1.6-5.1L5 10l5.4-1.9L12 3z" />
      <path d="M19 16l.7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16z" />
    </svg>
  );
}

export function DiceIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="4" y="4" width="16" height="16" rx="3" />
      <circle cx="8.5" cy="8.5" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="15.5" cy="8.5" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="8.5" cy="15.5" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="15.5" cy="15.5" r="0.8" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 4v10" />
      <path d="M8 10l4 4 4-4" />
      <path d="M5 19h14" />
    </svg>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 7h16" />
      <path d="M9 7V4h6v3" />
      <path d="M6 7l1 13h10l1-13" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  );
}

export function RefreshIcon(props: IconProps) {  return (
    <svg {...base(props)}>
      <path d="M20 11a8 8 0 1 0-2.3 5.7" />
      <path d="M20 4v7h-7" />
    </svg>
  );
}

export function StopIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 4l9 16H3L12 4z" />
      <path d="M12 9v4" />
      <path d="M12 16.5h.01" />
    </svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M5 12l4 4L19 6" />
    </svg>
  );
}

export function CpuIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="7" y="7" width="10" height="10" rx="2" />
      <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
      <rect x="10" y="10" width="4" height="4" rx="1" />
    </svg>
  );
}

export function LinkIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1" />
      <path d="M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1" />
    </svg>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4l3 2" />
    </svg>
  );
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

export function PaletteIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 4a8 8 0 0 0 0 16h1.5a2 2 0 0 0 0-4H12a2 2 0 0 1 0-4h4a4 4 0 0 0 0-8h-4z" />
      <circle cx="8" cy="9" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="7" cy="14" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="11" cy="7" r="0.8" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 8h.01" />
    </svg>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 16V4" />
      <path d="M7 9l5-5 5 5" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </svg>
  );
}

export function ImageIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="10" r="1.6" />
      <path d="M21 16l-5-5-9 9" />
    </svg>
  );
}

export function StudioIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 15l5-4 4 3 3-2 6 5" />
      <path d="M8 8h.01" />
    </svg>
  );
}

export function PlayIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6 4l14 8-14 8V4z" />
    </svg>
  );
}
