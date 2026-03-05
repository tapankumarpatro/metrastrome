"use client";

/* Unique illustrated face SVGs for each Tapan variant.
   Each face has distinct features (hair, glasses, expression) to be recognizable. */

interface FaceProps {
  className?: string;
}

/* 🚀 Visionary — confident, swept-back hair */
export function FaceVisionary({ className }: FaceProps) {
  return (
    <svg viewBox="0 0 120 120" className={className} fill="none">
      {/* Head */}
      <circle cx="60" cy="58" r="32" fill="#FFD6A0" />
      {/* Hair — swept back */}
      <path d="M28 50c0-20 14-34 32-34s32 14 32 34c0 2-1 4-2 5 1-18-12-31-30-31S30 37 31 55c-2-1-3-3-3-5z" fill="#4A3728" />
      <path d="M34 42c2-12 12-22 26-22s24 10 26 22c-4-8-14-14-26-14S38 34 34 42z" fill="#5C4433" />
      {/* Eyes */}
      <ellipse cx="47" cy="56" rx="3.5" ry="4" fill="#2D2D2D" />
      <ellipse cx="73" cy="56" rx="3.5" ry="4" fill="#2D2D2D" />
      <circle cx="48.5" cy="55" r="1.2" fill="white" />
      <circle cx="74.5" cy="55" r="1.2" fill="white" />
      {/* Eyebrows — confident */}
      <path d="M40 48c3-3 8-4 12-2" stroke="#4A3728" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M68 46c4-2 9-1 12 2" stroke="#4A3728" strokeWidth="2.5" strokeLinecap="round" />
      {/* Nose */}
      <path d="M57 60c1 4 3 6 3 6s2-2 3-6" stroke="#E8B886" strokeWidth="1.5" strokeLinecap="round" />
      {/* Smile — confident */}
      <path d="M48 72c4 5 10 6 16 4 2-1 4-2 5-4" stroke="#C4825A" strokeWidth="2" strokeLinecap="round" fill="none" />
      {/* Shoulders */}
      <path d="M20 105c0-18 18-28 40-28s40 10 40 28" fill="#6366F1" />
      {/* Collar */}
      <path d="M50 77l10 8 10-8" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/* 🏗️ Architect — glasses, neat hair parted to side */
export function FaceArchitect({ className }: FaceProps) {
  return (
    <svg viewBox="0 0 120 120" className={className} fill="none">
      <circle cx="60" cy="58" r="32" fill="#F5D0A9" />
      {/* Hair — neat, parted */}
      <path d="M28 48c0-20 14-34 32-34s32 14 32 34c0 3-1 5-3 7 2-20-11-33-29-33S31 35 33 55c-3-2-5-4-5-7z" fill="#2C1810" />
      <path d="M38 38c0-8 10-18 22-18 8 0 15 4 20 12-6-6-13-8-20-8-10 0-18 6-22 14z" fill="#3D2617" />
      {/* Glasses */}
      <rect x="36" y="50" width="18" height="14" rx="4" stroke="#555" strokeWidth="2.5" fill="none" />
      <rect x="66" y="50" width="18" height="14" rx="4" stroke="#555" strokeWidth="2.5" fill="none" />
      <path d="M54 56h12" stroke="#555" strokeWidth="2" />
      <path d="M36 55h-4" stroke="#555" strokeWidth="2" />
      <path d="M84 55h4" stroke="#555" strokeWidth="2" />
      {/* Eyes behind glasses */}
      <ellipse cx="45" cy="57" rx="3" ry="3.5" fill="#2D2D2D" />
      <ellipse cx="75" cy="57" rx="3" ry="3.5" fill="#2D2D2D" />
      <circle cx="46" cy="56" r="1" fill="white" />
      <circle cx="76" cy="56" r="1" fill="white" />
      {/* Eyebrows */}
      <path d="M38 47c3-2 7-2 11 0" stroke="#2C1810" strokeWidth="2" strokeLinecap="round" />
      <path d="M71 47c3-2 7-2 11 0" stroke="#2C1810" strokeWidth="2" strokeLinecap="round" />
      {/* Nose */}
      <path d="M58 61c1 3 2 5 2 5s1-2 2-5" stroke="#DDB48E" strokeWidth="1.5" strokeLinecap="round" />
      {/* Slight smile */}
      <path d="M50 72c3 3 8 4 12 3 2 0 4-1 5-3" stroke="#C4825A" strokeWidth="2" strokeLinecap="round" fill="none" />
      {/* Shoulders */}
      <path d="M20 105c0-18 18-28 40-28s40 10 40 28" fill="#7C3AED" />
      <path d="M50 77l10 8 10-8" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/* ⚡ Builder — casual, short hair, slight stubble */
export function FaceBuilder({ className }: FaceProps) {
  return (
    <svg viewBox="0 0 120 120" className={className} fill="none">
      <circle cx="60" cy="58" r="32" fill="#EDCBA0" />
      {/* Hair — short, spiky */}
      <path d="M30 50c0-18 13-32 30-32s30 14 30 32c0 2-1 3-2 4 0-16-12-28-28-28S32 38 32 54c-1-1-2-2-2-4z" fill="#1A1A2E" />
      <path d="M36 36l4-6m8-2l2-5m10 0l-1-5m10 2l2-5m8 4l4-5" stroke="#1A1A2E" strokeWidth="3" strokeLinecap="round" />
      {/* Eyes */}
      <ellipse cx="46" cy="56" rx="3.5" ry="4" fill="#2D2D2D" />
      <ellipse cx="74" cy="56" rx="3.5" ry="4" fill="#2D2D2D" />
      <circle cx="47.5" cy="55" r="1.2" fill="white" />
      <circle cx="75.5" cy="55" r="1.2" fill="white" />
      {/* Eyebrows — straight, focused */}
      <path d="M39 49h14" stroke="#1A1A2E" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M67 49h14" stroke="#1A1A2E" strokeWidth="2.5" strokeLinecap="round" />
      {/* Nose */}
      <path d="M57 60c1 4 3 6 3 6s2-2 3-6" stroke="#D4A87A" strokeWidth="1.5" strokeLinecap="round" />
      {/* Stubble dots */}
      <circle cx="48" cy="76" r="0.5" fill="#888" />
      <circle cx="52" cy="77" r="0.5" fill="#888" />
      <circle cx="56" cy="78" r="0.5" fill="#888" />
      <circle cx="60" cy="78" r="0.5" fill="#888" />
      <circle cx="64" cy="78" r="0.5" fill="#888" />
      <circle cx="68" cy="77" r="0.5" fill="#888" />
      <circle cx="72" cy="76" r="0.5" fill="#888" />
      {/* Grin */}
      <path d="M47 71c4 4 10 5 16 4 2-1 4-2 5-3" stroke="#C4825A" strokeWidth="2" strokeLinecap="round" fill="none" />
      {/* Shoulders — hoodie */}
      <path d="M20 105c0-18 18-28 40-28s40 10 40 28" fill="#3B82F6" />
      <path d="M52 77l8 6 8-6" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/* 🧬 Scientist — round glasses, curly/wavy hair */
export function FaceScientist({ className }: FaceProps) {
  return (
    <svg viewBox="0 0 120 120" className={className} fill="none">
      <circle cx="60" cy="58" r="32" fill="#F5D5B5" />
      {/* Hair — wavy/curly */}
      <path d="M28 52c0-22 14-36 32-36s32 14 32 36c0 2 0 3-1 4-1-20-13-32-31-32S30 36 31 56c-2-1-3-2-3-4z" fill="#8B4513" />
      <path d="M30 48c2-4 4-8 8-10m4-6c4-2 10-4 18-4 6 0 12 2 16 4m4 6c4 2 6 6 8 10" stroke="#A0522D" strokeWidth="3" strokeLinecap="round" />
      {/* Round glasses */}
      <circle cx="45" cy="57" r="10" stroke="#8B7355" strokeWidth="2" fill="none" />
      <circle cx="75" cy="57" r="10" stroke="#8B7355" strokeWidth="2" fill="none" />
      <path d="M55 57h10" stroke="#8B7355" strokeWidth="1.5" />
      <path d="M35 55h-3" stroke="#8B7355" strokeWidth="1.5" />
      <path d="M85 55h3" stroke="#8B7355" strokeWidth="1.5" />
      {/* Eyes */}
      <ellipse cx="45" cy="57" rx="3" ry="3.5" fill="#2D2D2D" />
      <ellipse cx="75" cy="57" rx="3" ry="3.5" fill="#2D2D2D" />
      <circle cx="46" cy="56" r="1" fill="white" />
      <circle cx="76" cy="56" r="1" fill="white" />
      {/* Raised eyebrows — curious */}
      <path d="M37 44c4-3 9-3 13 0" stroke="#8B4513" strokeWidth="2" strokeLinecap="round" />
      <path d="M70 44c4-3 9-3 13 0" stroke="#8B4513" strokeWidth="2" strokeLinecap="round" />
      {/* Nose */}
      <path d="M58 62c1 3 2 4 2 4s1-1 2-4" stroke="#DDB48E" strokeWidth="1.5" strokeLinecap="round" />
      {/* Excited smile */}
      <path d="M46 72c5 6 12 6 18 3 2-1 3-3 4-4" stroke="#C4825A" strokeWidth="2" strokeLinecap="round" fill="none" />
      {/* Shoulders — lab coat */}
      <path d="M20 105c0-18 18-28 40-28s40 10 40 28" fill="#10B981" />
      <path d="M50 77l10 8 10-8" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/* ⚙️ Machinist — strong jaw, buzz cut, serious */
export function FaceMachinist({ className }: FaceProps) {
  return (
    <svg viewBox="0 0 120 120" className={className} fill="none">
      {/* Slightly squarer jaw */}
      <path d="M28 55c0-18 14-32 32-32s32 14 32 32v5c0 12-8 22-18 26l-6 2c-5 2-11 2-16 0l-6-2c-10-4-18-14-18-26v-5z" fill="#E8C49A" />
      {/* Hair — buzz cut */}
      <path d="M30 50c0-18 13-30 30-30s30 12 30 30c-2-14-14-24-30-24S32 36 30 50z" fill="#333" />
      {/* Eyes — determined */}
      <ellipse cx="46" cy="56" rx="3.5" ry="3.5" fill="#2D2D2D" />
      <ellipse cx="74" cy="56" rx="3.5" ry="3.5" fill="#2D2D2D" />
      <circle cx="47.5" cy="55" r="1.2" fill="white" />
      <circle cx="75.5" cy="55" r="1.2" fill="white" />
      {/* Thick eyebrows — serious */}
      <path d="M38 48c4-3 10-3 14-1" stroke="#333" strokeWidth="3" strokeLinecap="round" />
      <path d="M68 47c4-2 10-2 14 1" stroke="#333" strokeWidth="3" strokeLinecap="round" />
      {/* Nose — broader */}
      <path d="M55 59c1 5 3 8 5 8s4-3 5-8" stroke="#D4A87A" strokeWidth="1.8" strokeLinecap="round" />
      {/* Firm mouth */}
      <path d="M49 73c4 2 9 2 14 1 3-1 5-2 6-3" stroke="#B87A5A" strokeWidth="2.2" strokeLinecap="round" fill="none" />
      {/* Shoulders */}
      <path d="M20 105c0-18 18-28 40-28s40 10 40 28" fill="#E11D48" />
      <path d="M50 80l10 6 10-6" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/* 📊 Datasmith — neat side-part, clean-shaven, friendly */
export function FaceDatasmith({ className }: FaceProps) {
  return (
    <svg viewBox="0 0 120 120" className={className} fill="none">
      <circle cx="60" cy="58" r="32" fill="#F0C8A0" />
      {/* Hair — neat side part */}
      <path d="M28 48c0-20 14-34 32-34s32 14 32 34c0 3-1 5-2 6 1-18-12-30-30-30S30 36 30 54c-1-2-2-4-2-6z" fill="#654321" />
      <path d="M42 20c-6 4-10 12-12 22 6-10 16-16 28-16 14 0 24 8 28 22 0-14-10-28-28-28-6 0-12 0-16 0z" fill="#7B5B3A" />
      {/* Eyes */}
      <ellipse cx="46" cy="56" rx="3" ry="3.5" fill="#2D2D2D" />
      <ellipse cx="74" cy="56" rx="3" ry="3.5" fill="#2D2D2D" />
      <circle cx="47" cy="55" r="1" fill="white" />
      <circle cx="75" cy="55" r="1" fill="white" />
      {/* Eyebrows — friendly */}
      <path d="M40 49c3-2 7-2 10 0" stroke="#654321" strokeWidth="2" strokeLinecap="round" />
      <path d="M70 49c3-2 7-2 10 0" stroke="#654321" strokeWidth="2" strokeLinecap="round" />
      {/* Nose */}
      <path d="M58 61c1 3 2 5 2 5s1-2 2-5" stroke="#DDB48E" strokeWidth="1.5" strokeLinecap="round" />
      {/* Warm smile */}
      <path d="M48 71c4 4 10 5 14 4 3-1 5-2 6-4" stroke="#C4825A" strokeWidth="2" strokeLinecap="round" fill="none" />
      {/* Dimples */}
      <circle cx="44" cy="72" r="1.5" fill="#DDB48E" />
      <circle cx="76" cy="72" r="1.5" fill="#DDB48E" />
      {/* Shoulders */}
      <path d="M20 105c0-18 18-28 40-28s40 10 40 28" fill="#0891B2" />
      <path d="M50 77l10 8 10-8" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/* 🎯 Strategist — sharp features, slicked-back hair */
export function FaceStrategist({ className }: FaceProps) {
  return (
    <svg viewBox="0 0 120 120" className={className} fill="none">
      <circle cx="60" cy="58" r="32" fill="#F2D0A9" />
      {/* Hair — slicked back */}
      <path d="M28 50c0-20 14-34 32-34s32 14 32 34c0 2 0 3-1 4 0-18-13-30-31-30S30 36 30 54c-1-1-2-3-2-4z" fill="#1C1C1C" />
      <path d="M32 44c4-14 14-22 28-22s24 8 28 22c-4-10-14-16-28-16S36 34 32 44z" fill="#2A2A2A" />
      {/* Eyes — sharp, focused */}
      <ellipse cx="46" cy="56" rx="3.5" ry="3" fill="#2D2D2D" />
      <ellipse cx="74" cy="56" rx="3.5" ry="3" fill="#2D2D2D" />
      <circle cx="47.5" cy="55.5" r="1.2" fill="white" />
      <circle cx="75.5" cy="55.5" r="1.2" fill="white" />
      {/* Angled eyebrows — strategic */}
      <path d="M38 49c4-4 10-4 14-1" stroke="#1C1C1C" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M68 48c4-3 10-3 14 1" stroke="#1C1C1C" strokeWidth="2.5" strokeLinecap="round" />
      {/* Nose */}
      <path d="M57 59c1 4 3 7 3 7s2-3 3-7" stroke="#DDB48E" strokeWidth="1.5" strokeLinecap="round" />
      {/* Knowing smirk */}
      <path d="M50 72c3 2 8 3 12 2 3-1 5-2 7-4" stroke="#C4825A" strokeWidth="2" strokeLinecap="round" fill="none" />
      {/* Shoulders */}
      <path d="M20 105c0-18 18-28 40-28s40 10 40 28" fill="#EA580C" />
      <path d="M50 77l10 8 10-8" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/* 🎨 Artist — longer messy hair, creative vibe */
export function FaceArtist({ className }: FaceProps) {
  return (
    <svg viewBox="0 0 120 120" className={className} fill="none">
      <circle cx="60" cy="58" r="32" fill="#F5D5C0" />
      {/* Hair — longer, messy, creative */}
      <path d="M24 55c0-24 16-38 36-38s36 14 36 38c0 2 0 3-1 4-2-22-15-34-35-34S28 37 26 59c-1-1-2-3-2-4z" fill="#C75000" />
      <path d="M26 50c2-4 4-8 6-10m4-6c2-2 6-6 12-8m12 0c6 2 10 6 12 8m4 6c2 2 4 6 6 10" stroke="#E06000" strokeWidth="3" strokeLinecap="round" />
      {/* Longer side strands */}
      <path d="M26 55c-2 6-2 12 0 16" stroke="#C75000" strokeWidth="4" strokeLinecap="round" />
      <path d="M94 55c2 6 2 12 0 16" stroke="#C75000" strokeWidth="4" strokeLinecap="round" />
      {/* Eyes — expressive, slightly larger */}
      <ellipse cx="45" cy="56" rx="4" ry="4.5" fill="#2D2D2D" />
      <ellipse cx="75" cy="56" rx="4" ry="4.5" fill="#2D2D2D" />
      <circle cx="46.5" cy="54.5" r="1.5" fill="white" />
      <circle cx="76.5" cy="54.5" r="1.5" fill="white" />
      {/* Eyebrows — expressive arches */}
      <path d="M37 47c4-4 10-4 14-1" stroke="#C75000" strokeWidth="2" strokeLinecap="round" />
      <path d="M69 46c4-3 10-3 14 1" stroke="#C75000" strokeWidth="2" strokeLinecap="round" />
      {/* Nose */}
      <path d="M58 61c1 3 2 5 2 5s1-2 2-5" stroke="#E0B898" strokeWidth="1.5" strokeLinecap="round" />
      {/* Big warm smile */}
      <path d="M44 71c6 6 14 7 20 4 2-1 4-3 5-5" stroke="#C4825A" strokeWidth="2" strokeLinecap="round" fill="none" />
      {/* Shoulders */}
      <path d="M20 105c0-18 18-28 40-28s40 10 40 28" fill="#DB2777" />
      <path d="M52 77l8 6 8-6" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/* Map agent IDs to face components */
export const AGENT_FACES: Record<string, React.FC<FaceProps>> = {
  "tapan-visionary": FaceVisionary,
  "tapan-architect": FaceArchitect,
  "tapan-builder": FaceBuilder,
  "tapan-scientist": FaceScientist,
  "tapan-machinist": FaceMachinist,
  "tapan-datasmith": FaceDatasmith,
  "tapan-strategist": FaceStrategist,
  "tapan-artist": FaceArtist,
};
