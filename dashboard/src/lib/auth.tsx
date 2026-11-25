import {
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut as fbSignOut,
  type User,
} from "firebase/auth";
import { FirebaseError } from "firebase/app";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { auth } from "./firebase";

interface AuthValue {
  user: User | null;
  loading: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signUpWithEmail: (email: string, password: string) => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

function requireAuth() {
  if (!auth) throw new Error("Firebase is not configured");
  return auth;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(auth));

  useEffect(() => {
    if (!auth) return;
    return onAuthStateChanged(auth, (u) => {
      setUser(u);
      setLoading(false);
    });
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      loading,
      signInWithGoogle: async () => {
        await signInWithPopup(requireAuth(), new GoogleAuthProvider());
      },
      signInWithEmail: async (email, password) => {
        await signInWithEmailAndPassword(requireAuth(), email, password);
      },
      signUpWithEmail: async (email, password) => {
        const cred = await createUserWithEmailAndPassword(requireAuth(), email, password);
        await sendEmailVerification(cred.user);
      },
      resetPassword: async (email) => {
        await sendPasswordResetEmail(requireAuth(), email);
      },
      signOut: async () => {
        await fbSignOut(requireAuth());
      },
    }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

/** The signed-in user's ID token for API calls (refreshed by Firebase when it expires). */
export async function idToken(): Promise<string> {
  const u = auth?.currentUser;
  if (!u) throw new Error("Not signed in");
  return u.getIdToken();
}

const MESSAGES: Record<string, string> = {
  "auth/invalid-credential": "Email or password is incorrect.",
  "auth/wrong-password": "Email or password is incorrect.",
  "auth/user-not-found": "No account with that email.",
  "auth/invalid-email": "Enter a valid email address.",
  "auth/email-already-in-use": "An account with this email already exists. Sign in instead.",
  "auth/weak-password": "Use at least 6 characters.",
  "auth/too-many-requests": "Too many attempts. Wait a minute and try again.",
  "auth/popup-closed-by-user": "",
  "auth/cancelled-popup-request": "",
  "auth/popup-blocked": "Your browser blocked the sign-in window. Allow pop-ups for this site and try again.",
  "auth/network-request-failed": "Network error. Check your connection.",
  "auth/operation-not-allowed": "This sign-in method is not enabled for the Firebase project.",
  "auth/unauthorized-domain": "This domain is not authorized in Firebase Authentication settings.",
};

/** A human message for a Firebase auth error; empty when there is nothing to tell the user. */
export function authErrorMessage(err: unknown): string {
  if (err instanceof FirebaseError) return MESSAGES[err.code] ?? "Sign-in failed. Try again.";
  return err instanceof Error ? err.message : "Sign-in failed. Try again.";
}
