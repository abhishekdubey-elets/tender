export type EventInfo = {
  type: string;
  type_label: string;
  title: string;
  value: number | null;
  org: string;
  department?: string | null;
  sector?: string | null;
  date?: string | null;
  reference?: string | null;
  location?: string | null;
};

export type LeadSummary = {
  id: string;
  company: string;
  status: string;
  event: EventInfo;
  opportunity: string;
  opportunity_tier: string;
  score: number;
  grade: string;
  confidence: number;
  why_now: string;
  reason_to_call: string;
  target_contact: string;
};

export type Evidence = {
  id: string;
  tier: string;
  statement: string;
  snippet?: string | null;
  source_url?: string | null;
  confidence?: number | null;
};

export type ScoreComponent = {
  key: string;
  points: number;
  max_points: number;
  note?: string | null;
};

export type BriefSection = {
  key: string;
  title: string;
  text: string;
  is_inference: boolean;
};

export type Contact = {
  name?: string | null;
  title?: string | null;
  verified: boolean;
  email?: string | null;
  linkedin?: string | null;
  source?: string | null;
  confidence?: number | null;
};

export type SourceDoc = { title: string; url: string; kind?: string | null; date?: string | null };

export type LeadDetail = LeadSummary & {
  company_profile: Record<string, any>;
  opportunity_detail: {
    need?: string;
    reasoning?: string;
    assumptions?: string[];
    alternatives?: string[];
    timing?: string;
    departments?: string[];
    job_titles?: string[];
    tier?: string;
  };
  evidence: Evidence[];
  score_components: ScoreComponent[];
  contact: Contact | null;
  brief: BriefSection[];
  risk?: string | null;
  sources: SourceDoc[];
};

export const FEEDBACK_ACTIONS = [
  { key: "lead_accepted", label: "Good lead", tone: "good" },
  { key: "lead_rejected", label: "Bad lead", tone: "bad" },
  { key: "contacted", label: "Contacted", tone: "info" },
  { key: "meeting_booked", label: "Meeting booked", tone: "accent" },
  { key: "not_relevant", label: "Not relevant", tone: "bad" },
  { key: "opportunity_created", label: "Opportunity created", tone: "good" },
] as const;
