import creativeTeam from "../../assets/illustrations/creative-team.svg";

/** Licensed Storyset artwork. Natural anatomy and proportions are kept intact. */
export function MakerScene() {
  return <img src={creativeTeam} width={500} height={500} alt="Ba bạn cùng nâng một ý tưởng: phối hợp quanh mô hình bóng đèn lớn." />;
}

/** Visible credit required by the free Storyset license on each consuming screen. */
export function ArtworkCredit() {
  return <a className="maker-art-credit" href="https://storyset.com/" target="_blank" rel="noreferrer">Minh họa: Storyset</a>;
}

/** Four related field-note illustrations carry the project through the journey. */
export function JourneySketch({ stage }: { stage: number }) {
  return (
    <svg viewBox="0 0 220 150" fill="none" aria-hidden="true">
      {stage === 0 && <>
        <path d="M46 122L158 119L178 132L58 136Z" fill="#DAE8FB" />
        <path d="M66 110L59 78H114L107 110Z" fill="#BD765B" />
        <path d="M87 78V38M87 58C70 59 58 46 66 36C82 34 88 46 87 58ZM88 47C88 30 108 24 116 31C115 45 102 50 88 47Z" stroke="#3E5BA3" strokeWidth="3" fill="#75CBD1" />
        <circle cx="147" cy="59" r="30" fill="#FFF8D2" stroke="#0C2D45" strokeWidth="3" />
        <path d="M167 81L183 100" stroke="#0C2D45" strokeWidth="9" strokeLinecap="round" />
        <path d="M139 48C139 39 157 38 157 48C157 55 148 54 148 61M148 69V71" stroke="#52647C" strokeWidth="3" strokeLinecap="round" />
      </>}
      {stage === 1 && <>
        <path d="M35 32L153 19L175 121L57 133Z" fill="#FFF8D2" stroke="#52647C" strokeWidth="2" />
        <path d="M52 53L147 42M56 67L151 56M60 81L155 70M64 95L159 84M68 109L163 98" stroke="#CDD7E7" />
        <path d="M80 100L76 70L100 51L130 63L134 93L110 109L80 100ZM76 70L105 82L130 63M105 82L110 109" stroke="#3E5BA3" strokeWidth="2" />
        <path d="M166 25L181 32L143 105L129 115L131 98Z" fill="#E1AE63" stroke="#9D794C" strokeWidth="2" />
        <path d="M129 115L133 103L140 107Z" fill="#0C2D45" />
        <path d="M62 28L75 132" stroke="#A97668" strokeWidth="2" />
      </>}
      {stage === 2 && <>
        <path d="M39 105L107 80L179 107L114 133Z" fill="#DAE8FB" />
        <path d="M55 63L113 77L160 58L103 40Z" fill="#DAE8FB" fillOpacity=".8" stroke="#3E5BA3" strokeWidth="2" />
        <path d="M55 63V106L113 123L160 103V58M113 77V123M55 63L77 32L103 22L128 49L160 58M77 32L128 49M103 22V40" stroke="#3E5BA3" strokeWidth="2" />
        <path d="M87 101V80M87 88C72 87 74 72 79 72C90 74 89 81 87 88ZM87 84C87 71 101 69 104 75C103 83 95 87 87 84Z" fill="#ABC689" stroke="#578458" strokeWidth="2" />
        <path d="M139 37L158 29L179 41L160 50Z" fill="#0C2D45" stroke="#CDD7E7" strokeWidth="2" />
        <path d="M154 31L174 44M143 39L166 34M158 50V62" stroke="#75CBD1" strokeWidth="1.5" />
        <circle cx="139" cy="99" r="4" fill="#FFF8D2" />
      </>}
      {stage === 3 && <>
        <path d="M43 29L142 22L152 113L53 122Z" fill="#EDE5C8" stroke="#A1AE91" strokeWidth="2" />
        <path d="M62 42L127 37L132 81L67 87Z" fill="#A8C3A5" />
        <path d="M79 72L100 49L121 69Z" fill="#618871" />
        <path d="M73 99L132 94M75 107L113 104" stroke="#A3AE8A" strokeWidth="2" />
        <path d="M140 78C141 59 164 51 179 61C195 73 188 95 174 99L160 100L148 110L148 94C143 91 140 86 140 78Z" fill="#EACA7D" />
        <path d="M156 79L164 84L176 70" stroke="#526B54" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      </>}
    </svg>
  );
}
