"use client";

import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Flame, IndianRupee, Target, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { LeadCard } from "@/components/lead-card";
import { LeadDrawer } from "@/components/lead-drawer";
import { CountUp, Skeleton } from "@/components/ui";
import { getLead, getLeads, sendFeedback, type Filters } from "@/lib/api";
import type { LeadDetail, LeadSummary } from "@/lib/types";

type Options = { sectors: string[]; products: string[]; eventTypes: string[]; orgs: string[] };
const uniq = (xs: (string | null | undefined)[]) =>
  Array.from(new Set(xs.filter(Boolean) as string[])).sort();

const container = { hidden: {}, show: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } } };

function Stat({ icon: Icon, value, prefix, suffix, label, color, delay }: any) {
  return (
    <motion.div
      className="stat-card glass"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="glow" style={{ background: color }} />
      <div className="ic" style={{ background: `color-mix(in srgb, ${color} 20%, transparent)`, color }}>
        <Icon size={18} />
      </div>
      <div className="val mono">
        {prefix}
        <CountUp value={value} />
        {suffix}
      </div>
      <div className="lbl">{label}</div>
    </motion.div>
  );
}

export default function Page() {
  const [filters, setFilters] = useState<Filters>({});
  const [search, setSearch] = useState("");
  const [leads, setLeads] = useState<LeadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(true);
  const [options, setOptions] = useState<Options>({ sectors: [], products: [], eventTypes: [], orgs: [] });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // options (once)
  useEffect(() => {
    getLeads({})
      .then((all) => {
        setOnline(true);
        setOptions({
          sectors: uniq(all.map((l) => l.event.sector)),
          products: uniq(all.map((l) => l.opportunity)),
          eventTypes: uniq(all.map((l) => l.event.type_label)),
          orgs: uniq(all.map((l) => l.event.org)),
        });
      })
      .catch(() => setOnline(false));
  }, []);

  // debounce search into the company filter
  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => ({ ...f, company: search || undefined })), 280);
    return () => clearTimeout(t);
  }, [search]);

  // leads on filter change
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getLeads(filters)
      .then((ls) => !cancelled && (setLeads(ls), setOnline(true)))
      .catch(() => !cancelled && setOnline(false))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [filters]);

  const stats = useMemo(() => {
    const n = leads.length;
    const avg = n ? Math.round(leads.reduce((s, l) => s + l.score, 0) / n) : 0;
    const hot = leads.filter((l) => l.score >= 80).length;
    const pipeCr = Math.round(leads.reduce((s, l) => s + (l.event.value || 0), 0) / 1e7);
    return { n, avg, hot, pipeCr };
  }, [leads]);

  async function open(id: string) {
    setSelectedId(id);
    setDetail(null);
    setDetailLoading(true);
    try {
      setDetail(await getLead(id));
    } catch {
      setToast("Could not load lead detail");
    } finally {
      setDetailLoading(false);
    }
  }
  const close = () => setSelectedId(null);

  async function feedback(id: string, eventType: string) {
    try {
      const { status } = await sendFeedback(id, eventType);
      setDetail((d) => (d ? { ...d, status } : d));
      setLeads((ls) => ls.map((l) => (l.id === id ? { ...l, status } : l)));
      const label = eventType.replace(/_/g, " ");
      setToast(`Recorded “${label}” → status “${status}”`);
    } catch {
      setToast("Feedback failed");
    }
  }

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  const set = (k: keyof Filters) => (e: React.ChangeEvent<HTMLSelectElement>) =>
    setFilters((f) => ({ ...f, [k]: e.target.value || undefined }));

  const Select = ({ k, label, opts }: { k: keyof Filters; label: string; opts: string[] }) => (
    <div className="fld">
      <label>{label}</label>
      <select value={(filters[k] as string) || ""} onChange={set(k)}>
        <option value="">All</option>
        {opts.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <AppShell search={search} onSearch={setSearch} online={online}>
      <motion.div className="page-head" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <h2>High-priority leads</h2>
        <p>Companies that just won government money — why it's an opening, and who to call.</p>
      </motion.div>

      <div className="stat-row">
        <Stat icon={Target} value={stats.n} label="Active leads" color="var(--accent)" delay={0.05} />
        <Stat icon={TrendingUp} value={stats.avg} label="Average score" color="var(--info)" delay={0.1} />
        <Stat icon={Flame} value={stats.hot} label="Hot leads (80+)" color="var(--warn)" delay={0.15} />
        <Stat icon={IndianRupee} value={stats.pipeCr} suffix=" cr" label="Pipeline value" color="var(--good)" delay={0.2} />
      </div>

      <motion.div
        className="filters glass"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <div className="scorebox">
          <label>Min score · {filters.score_min || 0}</label>
          <div className="row">
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={filters.score_min || 0}
              onChange={(e) => setFilters((f) => ({ ...f, score_min: Number(e.target.value) || undefined }))}
            />
          </div>
        </div>
        <Select k="sector" label="Sector" opts={options.sectors} />
        <Select k="product" label="Product" opts={options.products} />
        <Select k="event_type" label="Event type" opts={options.eventTypes} />
        <Select k="gov_org" label="Government org" opts={options.orgs} />
        <div className="fld">
          <label>Status</label>
          <select value={filters.status || ""} onChange={set("status")}>
            <option value="">Any</option>
            {["new", "qualified", "contacted", "meeting", "disqualified"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <button
          className="reset-btn"
          onClick={() => {
            setFilters({});
            setSearch("");
          }}
        >
          Reset
        </button>
      </motion.div>

      <div className="board-label">
        <h3>Leads</h3>
        <span>{loading ? "loading…" : `${leads.length} shown · sorted by score`}</span>
      </div>

      {loading ? (
        <div className="lead-grid">
          {[0, 1, 2].map((i) => (
            <div key={i} className="lead-card glass" style={{ display: "block", padding: 18 }}>
              <Skeleton h={20} w="45%" style={{ marginBottom: 12 }} />
              <Skeleton h={14} w="70%" style={{ marginBottom: 16 }} />
              <Skeleton h={12} w="90%" />
            </div>
          ))}
        </div>
      ) : leads.length === 0 ? (
        <motion.div className="empty glass" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <div className="big">{online ? "No leads match these filters" : "Can't reach the API"}</div>
          <div>{online ? "Try lowering the minimum score or clearing a filter." : "Make sure the backend is running on port 8000."}</div>
        </motion.div>
      ) : (
        <motion.div className="lead-grid" variants={container} initial="hidden" animate="show" layout>
          <AnimatePresence>
            {leads.map((l) => (
              <LeadCard key={l.id} lead={l} onOpen={open} />
            ))}
          </AnimatePresence>
        </motion.div>
      )}

      <LeadDrawer open={selectedId != null} detail={detail} loading={detailLoading} onClose={close} onFeedback={feedback} />

      <AnimatePresence>
        {toast && (
          <motion.div
            className="toast"
            initial={{ opacity: 0, y: 20, x: "-50%" }}
            animate={{ opacity: 1, y: 0, x: "-50%" }}
            exit={{ opacity: 0, y: 20, x: "-50%" }}
          >
            <CheckCircle2 size={16} color="var(--good)" />
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </AppShell>
  );
}
