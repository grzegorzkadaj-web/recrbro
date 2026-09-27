export function LogoMark() {
  return (
    <span className="logo" aria-hidden="true">
      <svg viewBox="0 0 64 64">
        <path
          className="logoHeadset"
          d="M16 31v-5C16 13 22 6 32 6s16 7 16 20v5"
        />
        <rect className="logoFace" x="15" y="17" width="34" height="31" rx="11" />
        <rect className="logoEarpiece" x="11" y="28" width="7" height="14" rx="3.5" />
        <rect className="logoEarpiece" x="46" y="28" width="7" height="14" rx="3.5" />
        <circle className="logoEye" cx="26" cy="32" r="2.7" />
        <circle className="logoEye" cx="38" cy="32" r="2.7" />
        <path className="logoSmile" d="M25 39c3 4 11 4 14 0" />
        <path className="logoMic" d="M51 40c0 7-5 10-11 10" />
        <circle className="logoMicDot" cx="39" cy="50" r="2.5" />
        <path className="logoShirt" d="M18 55c4-4 9-6 14-6s10 2 14 6v9H18z" />
        <path className="logoTie" d="m29 50 3 7 3-7z" />
      </svg>
    </span>
  );
}

export function BrandLogo() {
  return (
    <>
      <LogoMark />
      <span className="brandCopy">
        <span className="brandName">
          Recr<span>Bro</span>
        </span>
        <span className="brandTagline">Your recruiting bro.</span>
      </span>
    </>
  );
}
