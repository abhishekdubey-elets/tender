import type { LeadDetail, LeadSummary } from "./types";

export type Filters = {
  score_min?: number;
  sector?: string;
  product?: string;
  event_type?: string;
  gov_org?: string;
  status?: string;
  company?: string;
};

function qs(filters: Filters): string {
  const p = new URLSearchParams();
  if (filters.score_min) p.set("score_min", String(filters.score_min));
  for (const k of ["sector", "product", "event_type", "gov_org", "status", "company"] as const) {
    const v = filters[k];
    if (v) p.set(k, v);
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export async function getLeads(filters: Filters): Promise<LeadSummary[]> {
  return j(await fetch(`/api/leads${qs(filters)}`, { cache: "no-store" }));
}

export async function getLead(id: string): Promise<LeadDetail> {
  return j(await fetch(`/api/leads/${id}`, { cache: "no-store" }));
}

export async function sendFeedback(id: string, eventType: string): Promise<{ status: string }> {
  return j(
    await fetch(`/api/leads/${id}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_type: eventType }),
    }),
  );
}

export const money = (v: number | null | undefined): string =>
  v == null ? "—" : v >= 1e7 ? `₹${(v / 1e7).toFixed(v >= 1e8 ? 0 : 1)} cr` : `₹${Number(v).toLocaleString("en-IN")}`;

export const host = (u?: string | null): string => {
  if (!u) return "";
  try {
    return new URL(u).host;
  } catch {
    return u;
  }
};
