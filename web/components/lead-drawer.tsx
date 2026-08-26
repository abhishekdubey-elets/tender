"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ExternalLink, X } from "lucide-react";
import { host, money } from "@/lib/api";
import { FEEDBACK_ACTIONS, type LeadDetail } from "@/lib/types";
import { gradeClass, Skeleton } from "./ui";

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05, delayChildren: 0.08 } },
};
const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 300, damping: 30 } },
};

function Section({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <motion.section className="sec" variants={item}>
      <h4>
        <span className="n">{n}</span>
        {title}
      </h4>
      {children}
    </motion.section>
  );
}

export function LeadDrawer({
  open,
  detail,
  loading,
  onClose,
  onFeedback,
}: {
  open: boolean;
  detail: LeadDetail | null;
  loading: boolean;
  onClose: () => void;
  onFeedback: (id: string, eventType: string) => void;
}) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="scrim"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            className={`drawer ${detail ? gradeClass(detail.grade) : ""}`}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
          >
            {loading || !detail ? (
              <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
                <Skeleton h={26} w="60%" />
                <Skeleton h={90} />
                <Skeleton h={140} />
                <Skeleton h={120} />
              </div>
            ) : (
              <>
                <div className="drawer-head">
                  <div>
                    <p className="co">{detail.company}</p>
                    <p className="sub">
                      {detail.event.type_label} · {detail.event.org} ·{" "}
                      <span className="status-pill">{detail.status}</span>
                    </p>
                  </div>
                  <div className="chip">
                    <div className="big">{detail.score}</div>
                    <span className="grade-pill">Grade {detail.grade}</span>
                  </div>
                  <button className="icon-btn" onClick={onClose} aria-label="Close">
                    <X size={17} />
                  </button>
                </div>

                <motion.div className="drawer-body" variants={stagger} initial="hidden" animate="show">
                  <Section n={1} title="Government event">
                    <dl className="kv">
                      <dt>Event</dt><dd>{detail.event.title}</dd>
                      <dt>Value</dt><dd><span className="money">{money(detail.event.value)}</span></dd>
                      <dt>Government org</dt><dd>{detail.event.org}</dd>
                      <dt>Department</dt><dd>{detail.event.department || "—"}</dd>
                      <dt>Sector</dt><dd>{detail.event.sector || "—"}</dd>
                      <dt>Date</dt><dd>{detail.event.date || "—"}</dd>
                      <dt>Reference</dt><dd className="mono">{detail.event.reference || "—"}</dd>
                      <dt>Location</dt><dd>{detail.event.location || "—"}</dd>
                    </dl>
                  </Section>

                  <Section n={2} title="Evidence — every claim links to its source">
                    {detail.evidence.length === 0 && <p className="reason">No evidence on file.</p>}
                    {detail.evidence.map((e) => (
                      <div className="ev" key={e.id}>
                        <span className="fid">{e.id}</span>
                        <div>
                          <p className="stmt">
                            {e.statement}{" "}
                            <span className={`badge ${e.tier === "fact" ? "fact" : "infer"}`}>{e.tier}</span>
                          </p>
                          <div className="src">
                            {e.source_url ? (
                              <a href={e.source_url} target="_blank" rel="noopener noreferrer">
                                {host(e.source_url)} <ExternalLink size={11} style={{ verticalAlign: "-1px" }} />
                              </a>
                            ) : (
                              <span>no source URL</span>
                            )}
                            {e.confidence != null && <span>· conf {e.confidence.toFixed(2)}</span>}
                          </div>
                        </div>
                      </div>
                    ))}
                  </Section>

                  <Section n={3} title="Company profile">
                    <p className="reason" style={{ marginBottom: 10 }}>
                      {detail.company_profile.description || ""}
                    </p>
                    <dl className="kv">
                      <dt>Industry</dt><dd>{detail.company_profile.industry || "—"}</dd>
                      <dt>Headquarters</dt><dd>{detail.company_profile.hq || "—"}</dd>
                      <dt>Employees</dt><dd>{detail.company_profile.size || "—"}</dd>
                      <dt>Revenue</dt><dd>{detail.company_profile.revenue ? money(detail.company_profile.revenue) : "—"}</dd>
                      <dt>Website</dt>
                      <dd>
                        {detail.company_profile.website ? (
                          <a href={detail.company_profile.website} target="_blank" rel="noopener noreferrer">
                            {host(detail.company_profile.website)} <ExternalLink size={11} style={{ verticalAlign: "-1px" }} />
                          </a>
                        ) : "—"}
                      </dd>
                    </dl>
                  </Section>

                  <Section n={4} title="Opportunity reasoning">
                    <p className="opp" style={{ marginBottom: 8 }}>
                      {detail.opportunity} — {detail.opportunity_detail.need}
                      <span className={`badge ${detail.opportunity_tier === "inference" ? "infer" : "fact"}`}>
                        {detail.opportunity_tier}
                      </span>
                    </p>
                    <p className="reasoning">{detail.opportunity_detail.reasoning}</p>
                    {(detail.opportunity_detail.assumptions || []).map((a, i) => (
                      <p className="assum" key={"a" + i}><span className="tag">Assumption:</span> {a}</p>
                    ))}
                    {(detail.opportunity_detail.alternatives || []).map((a, i) => (
                      <p className="assum alt" key={"x" + i}><span className="tag">Alternative:</span> {a}</p>
                    ))}
                    {detail.opportunity_detail.timing && (
                      <p style={{ fontSize: 12.5, color: "var(--faint)", marginTop: 8 }}>
                        Timing {detail.opportunity_detail.timing}
                      </p>
                    )}
                  </Section>

                  <Section n={5} title={`Score breakdown — why ${detail.score} / 100`}>
                    {detail.score_components.map((c, i) => (
                      <div className="comp" key={c.key}>
                        <div>
                          {c.key}
                          <small>{c.note}</small>
                        </div>
                        <div className="track">
                          <motion.div
                            className="fill"
                            initial={{ width: 0 }}
                            animate={{ width: `${Math.round((c.points / c.max_points) * 100)}%` }}
                            transition={{ duration: 0.7, delay: 0.15 + i * 0.06, ease: [0.16, 1, 0.3, 1] }}
                          />
                        </div>
                        <div className="pts mono">{c.points}/{c.max_points}</div>
                      </div>
                    ))}
                  </Section>

                  <Section n={6} title="Contact">
                    {detail.contact ? (
                      <dl className="kv">
                        <dt>Name</dt>
                        <dd>
                          {detail.contact.name}{" "}
                          {detail.contact.verified && <span className="badge fact">verified</span>}
                        </dd>
                        <dt>Title</dt><dd>{detail.contact.title || "—"}</dd>
                        <dt>Email</dt>
                        <dd>{detail.contact.email ? <a href={`mailto:${detail.contact.email}`}>{detail.contact.email}</a> : "—"}</dd>
                        <dt>LinkedIn</dt>
                        <dd>{detail.contact.linkedin ? <a href={detail.contact.linkedin} target="_blank" rel="noopener noreferrer">profile ↗</a> : "—"}</dd>
                      </dl>
                    ) : (
                      <p className="reason">
                        No verified contact yet — target roles:{" "}
                        {(detail.opportunity_detail.job_titles || []).join(", ") || "decision-makers"}.
                      </p>
                    )}
                  </Section>

                  <Section n={7} title="AI sales brief">
                    {detail.brief.map((b) => (
                      <div className="brief-sec" key={b.key}>
                        <h5>
                          {b.title} {b.is_inference && <span className="inf-tag">inferred</span>}
                        </h5>
                        <p>{b.text}</p>
                      </div>
                    ))}
                    {detail.risk && (
                      <div className="risk">
                        <h5>Risk / uncertainty</h5>
                        <p>{detail.risk}</p>
                      </div>
                    )}
                  </Section>

                  <Section n={8} title="Source documents">
                    {detail.sources.map((d, i) => (
                      <div className="doc" key={i}>
                        <span className="kind">{d.kind || "doc"}</span>
                        <a href={d.url} target="_blank" rel="noopener noreferrer">
                          {d.title} <ExternalLink size={11} style={{ verticalAlign: "-1px" }} />
                        </a>
                      </div>
                    ))}
                  </Section>
                </motion.div>

                <div className="feedback">
                  {FEEDBACK_ACTIONS.map((a) => (
                    <motion.button
                      key={a.key}
                      className={`fb ${a.tone}`}
                      whileTap={{ scale: 0.94 }}
                      onClick={() => onFeedback(detail.id, a.key)}
                    >
                      {a.label}
                    </motion.button>
                  ))}
                </div>
              </>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
