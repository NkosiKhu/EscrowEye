import { useState } from "react";
import type { ApiUser } from "../../types";
import { defaultProfile } from "../workspace/demoData";
import type { Profile } from "../workspace/models";
import { readStored } from "../../services/storage";

const TOKEN_KEY = "escroweye.token";
const USER_KEY = "escroweye.user";
const PROFILE_KEY = "escroweye.profile";

export function useSession() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<ApiUser | null>(() => readStored<ApiUser>(USER_KEY));
  const [profile, setProfile] = useState<Profile>(() => readStored<Profile>(PROFILE_KEY) ?? defaultProfile);

  function persistSession(nextToken: string, nextUser: ApiUser, nextProfile: Profile) {
    localStorage.setItem(TOKEN_KEY, nextToken);
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser));
    localStorage.setItem(PROFILE_KEY, JSON.stringify(nextProfile));
    setToken(nextToken);
    setUser(nextUser);
    setProfile(nextProfile);
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
  }

  return {
    token,
    user,
    profile,
    persistSession,
    clearSession,
  };
}
