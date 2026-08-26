"use client";

import { motion } from "framer-motion";
import { forwardRef } from "react";
import { money } from "@/lib/api";
import type { LeadSummary } from "@/lib/types";
import { gradeClass, ScoreRing } from "./ui";

export const LeadCard = forwardRef<HTMLElement, { lead: LeadSummary; onOpen: (id: string) => void }>(
  function LeadCard({ lead, onOpen }, ref) {
  return (
    <motion.article
      ref={ref}
      layout
      layoutId={`lead-${lead.id}`}
      className={`lead-card glass ${gradeClass(lead.grade)}`}
      variants={{
        hidden: { opacity: 0, y: 16, scale: 0.98 },
        show: { opacity: 1, y: 0, scale: 1 },
      }}
      whileHover={{ y: -3, boxShadow: "var(--shadow-lg)" }}
      transition={{ type: "spring", stiffness: 260, damping: 26 }}
      onClick={() => onOpen(lead.id)}
    >
      <div className="col">
        <h4 className="company">{lead.company}</h4>
        <p className="evline">
          <span className="etype">{lead.event.type_label}:</span> {lead.event.title}
        </p>
        <div className="meta">
          <span>
            <span className="k">Value</span> <span className="money">{money(lead.event.value)}</span>
          </span>
          <span>
            <span className="k">Gov org</span> {lead.event.org}
          </span>
          <span>
            <span className="k">Sector</span> {lead.event.sector || "—"}
          </span>
          <span>
            <span className="k">Dated</span> {lead.event.date || "—"}
          </span>
        </div>
      </div>

      <div className="col mid">
        <p className="klbl">Opportunity</p>
        <p className="opp">
          {lead.opportunity}
          <span className={`badge ${lead.opportunity_tier === "inference" ? "infer" : "fact"}`}>
            {lead.opportunity_tier}
          </span>
        </p>
        <p className="whynow">
          <b>Why now:</b> {lead.why_now}
        </p>
        <p className="klbl">Target contact</p>
        <p className="reason" style={{ marginBottom: 8 }}>
          {lead.target_contact}
        </p>
        <p className="reason">
          <b>Reason to call:</b> {lead.reason_to_call}
        </p>
      </div>

      <div className="col right">
        <ScoreRing value={lead.score} grade={lead.grade} />
        <span className="grade-pill">Grade {lead.grade}</span>
        <span className="conf">confidence {Math.round((lead.confidence || 0) * 100)}%</span>
        <span className="status-pill">{lead.status}</span>
        <button className="view-btn" onClick={(e) => (e.stopPropagation(), onOpen(lead.id))}>
          View lead
        </button>
      </div>
    </motion.article>
  );
});
