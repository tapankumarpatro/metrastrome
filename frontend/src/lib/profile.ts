/**
 * User profile — stored in localStorage.
 * The "About Me" section in settings populates this.
 * Other pages gate on `isProfileComplete()`.
 */

const PROFILE_KEY = "metrastrome_user_profile";

export interface UserProfile {
  name: string;
  bio: string;        // short description about the user
  expertise: string;  // comma-separated areas
  photo: string;      // base64 data URI of reference photo (or empty)
  videoMode: boolean;  // enable MuseTalk video avatars (requires GPU on server)
}

const EMPTY_PROFILE: UserProfile = { name: "", bio: "", expertise: "", photo: "", videoMode: false };

export function getProfile(): UserProfile {
  if (typeof window === "undefined") return EMPTY_PROFILE;
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return EMPTY_PROFILE;
    return { ...EMPTY_PROFILE, ...JSON.parse(raw) };
  } catch {
    return EMPTY_PROFILE;
  }
}

export function saveProfile(profile: UserProfile): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}

export function isProfileComplete(): boolean {
  const p = getProfile();
  return p.name.trim().length > 0;
}
