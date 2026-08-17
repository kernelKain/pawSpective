export function PawSpectiveLogo({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`logo-lockup${compact ? " compact" : ""}`} aria-hidden="true">
      <svg className="logo-symbol" viewBox="0 0 64 64" role="img">
        <path d="M11 31C18 18 29 12 42 15c7 2 12 7 15 14-5 12-15 20-28 20-8 0-14-6-18-18Z" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
        <circle cx="34" cy="31" r="7" fill="currentColor" />
        <circle cx="19" cy="13" r="4" fill="currentColor" />
        <circle cx="29" cy="9" r="4" fill="currentColor" />
        <circle cx="40" cy="10" r="4" fill="currentColor" />
      </svg>
    </span>
  );
}
