"use client";

import { motion } from "framer-motion";
import { BarChart3, Building2, Radar, Search, Settings, Target } from "lucide-react";
import { ThemeToggle } from "./ui";

const NAV = [
  { icon: Target, label: "Leads", active: true },
  { icon: Building2, label: "Companies", active: false },
  { icon: Radar, label: "Signals", active: false },
  { icon: BarChart3, label: "Analytics", active: false },
  { icon: Settings, label: "Settings", active: false },
];

export function AppShell({
  search,
  onSearch,
  online,
  children,
}: {
  search: string;
  onSearch: (v: string) => void;
  online: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="app">
      <motion.aside
        className="sidebar"
        initial={{ x: -24, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="logo">
          <div className="mark">GI</div>
          <div>
            <h1>GovIntel</h1>
            <p>Sales Intelligence</p>
          </div>
        </div>

        <nav className="nav">
          <div className="lbl">Workspace</div>
          {NAV.map((item, i) => (
            <motion.a
              key={item.label}
              href="#"
              className={item.active ? "active" : ""}
              onClick={(e) => e.preventDefault()}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.15 + i * 0.05 }}
              whileHover={{ x: item.active ? 0 : 3 }}
            >
              {item.active && <motion.span layoutId="nav-active" className="active-bg" />}
              <span>
                <item.icon size={17} />
                {item.label}
              </span>
            </motion.a>
          ))}
        </nav>

        <div className="foot">
          <div className="userbox">
            <div className="avatar">DE</div>
            <div>
              <div className="nm">Elets Technomedia</div>
              <div className="rl">analyst · demo</div>
            </div>
          </div>
        </div>
      </motion.aside>

      <div className="main">
        <div className="topbar">
          <div className="search">
            <Search size={16} />
            <input
              value={search}
              onChange={(e) => onSearch(e.target.value)}
              placeholder="Search companies…"
              aria-label="Search companies"
            />
          </div>
          <div className="spacer" />
          <motion.div
            className="status-chip"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <span className={`dot ${online ? "" : "err"}`} />
            {online ? "Live · Postgres" : "API offline"}
          </motion.div>
          <ThemeToggle />
        </div>

        <div className="content">{children}</div>
      </div>
    </div>
  );
}
