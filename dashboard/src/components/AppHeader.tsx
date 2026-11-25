import { useEffect, useRef, useState } from "react";
import { useAuth } from "../lib/auth";
import { Link, navigate } from "../lib/router";
import { Brand } from "./Brand";

export function AppHeader({ children }: { children?: React.ReactNode }) {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !menu.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const initial = (user?.displayName || user?.email || "?").charAt(0).toUpperCase();

  return (
    <header className="app-header">
      <Brand href="/app" />
      <div className="app-header-right">
        {children}
        <div className="user-menu" ref={menu}>
          <button className="avatar" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)} title={user?.email ?? ""}>
            {user?.photoURL ? <img src={user.photoURL} alt="" referrerPolicy="no-referrer" /> : initial}
          </button>
          {open && (
            <div className="menu" role="menu">
              <div className="menu-id">
                <strong>{user?.displayName || "Signed in"}</strong>
                <span>{user?.email}</span>
              </div>
              <Link href="/" role="menuitem" className="menu-item">
                Home
              </Link>
              <button
                role="menuitem"
                className="menu-item"
                onClick={async () => {
                  await signOut();
                  navigate("/");
                }}
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
