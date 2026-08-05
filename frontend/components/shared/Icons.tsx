/**
 * Icon set
 *
 * Inline SVG rather than an icon package: the whole app is otherwise
 * dependency-light, and these render identically offline. All icons are drawn
 * on a 24x24 grid with `currentColor` strokes, so they inherit text colour and
 * work in both themes without variants.
 */

import React from 'react';

export interface IconProps extends React.SVGProps<SVGSVGElement> {
  /** Rendered size in px, applied to both axes. */
  size?: number;
}

const Svg: React.FC<IconProps & { children: React.ReactNode }> = ({
  size = 20,
  children,
  ...rest
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.75}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    focusable="false"
    {...rest}
  >
    {children}
  </svg>
);

/** Scales of justice — the product mark. */
export const ScalesIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M12 3v18" />
    <path d="M7 21h10" />
    <path d="M5 7h14" />
    <path d="M5 7l-3 6h6L5 7Z" />
    <path d="M19 7l-3 6h6l-3-6Z" />
  </Svg>
);

export const ChatIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M21 12a8 8 0 0 1-8 8H8l-4 3v-4.5A8 8 0 0 1 13 4a8 8 0 0 1 8 8Z" />
    <path d="M9 11h8M9 15h5" />
  </Svg>
);

export const SearchIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.6-3.6" />
  </Svg>
);

/** Live research: a globe, to distinguish "off-machine" from local search. */
export const GlobeIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3.5 9h17M3.5 15h17" />
    <path d="M12 3c2.4 2.5 3.6 5.5 3.6 9s-1.2 6.5-3.6 9c-2.4-2.5-3.6-5.5-3.6-9S9.6 5.5 12 3Z" />
  </Svg>
);

export const DraftIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M14 3v5h5" />
    <path d="M19 10.5V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h7.5L19 8.5Z" />
    <path d="M9 13h6M9 17h4" />
  </Svg>
);

export const AnalyzeIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M14 3v5h5" />
    <path d="M19 10.5V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h7.5L19 8.5Z" />
    <circle cx="11.5" cy="14.5" r="2.5" />
    <path d="m14 17 2 2" />
  </Svg>
);

export const SendIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M4 12 20 4l-8 16-2-6-6-2Z" />
  </Svg>
);

export const SunIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19" />
  </Svg>
);

export const MoonIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />
  </Svg>
);

export const CheckIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="m4 12.5 5 5L20 6.5" />
  </Svg>
);

export const CloseIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
);

export const AlertIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M12 4l9 16H3l9-16Z" />
    <path d="M12 10v4M12 17.5v.5" />
  </Svg>
);

export const InfoIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 7.5v.5" />
  </Svg>
);

export const CopyIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <rect x="9" y="9" width="11" height="11" rx="2" />
    <path d="M15 5.5A1.5 1.5 0 0 0 13.5 4H6a2 2 0 0 0-2 2v7.5A1.5 1.5 0 0 0 5.5 15" />
  </Svg>
);

export const DownloadIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" />
    <path d="M5 19h14" />
  </Svg>
);

export const ExternalIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M14 4h6v6" />
    <path d="M20 4l-8.5 8.5" />
    <path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" />
  </Svg>
);

export const ChevronDownIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
);

export const MenuIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Svg>
);

export const BookIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H5.5A1.5 1.5 0 0 1 4 15.5v-10Z" />
    <path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H14a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h4.5a1.5 1.5 0 0 0 1.5-1.5v-10Z" />
  </Svg>
);

export const ResetIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M4 12a8 8 0 1 0 2.8-6.1" />
    <path d="M4 4v4h4" />
  </Svg>
);
