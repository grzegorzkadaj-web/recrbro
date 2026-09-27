export function LegalFooter({ compact = false }: { compact?: boolean }) {
  return (
    <footer className={compact ? "legalFooter compactFooter" : "legalFooter"}>
      <span>
        Job sources are collected through Tavily. RecrBro is not responsible
        for their quality, completeness, or accuracy.
      </span>
      <nav aria-label="Legal">
        <a href="/terms">Terms of Service</a>
        <a href="/privacy-policy">Privacy Policy</a>
      </nav>
    </footer>
  );
}
