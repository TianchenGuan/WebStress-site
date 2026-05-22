import type { Primitive, Environment, Difficulty } from "../data/types";

export const PRIMITIVE_LABELS: Record<Primitive, string> = {
  grounding: "Grounding",
  planning: "Planning",
  state_tracking: "State tracking",
  backtracking: "Backtracking",
  patience: "Patience",
  exploration: "Exploration",
  verification: "Verification",
};

export const ENV_LABELS: Record<Environment, string> = {
  gmail: "Gmail",
  amazon: "Amazon",
  reddit: "Reddit",
  robinhood: "Robinhood",
  booking: "Booking",
  lms: "LMS",
  patient_portal: "Patient Portal",
};

export const ENV_DOMAINS: Record<Environment, string> = {
  gmail: "Email",
  amazon: "E-commerce",
  reddit: "Social",
  robinhood: "Finance",
  booking: "Travel",
  lms: "Education",
  patient_portal: "Healthcare",
};

export const DIFFICULTY_ORDER: Difficulty[] = [
  "easy",
  "medium",
  "hard",
  "expert",
  "frontier",
];

export const PRIMITIVE_ORDER: Primitive[] = [
  "grounding",
  "planning",
  "state_tracking",
  "backtracking",
  "patience",
  "exploration",
  "verification",
];

export const ENV_ORDER: Environment[] = [
  "gmail",
  "amazon",
  "reddit",
  "robinhood",
  "booking",
  "lms",
  "patient_portal",
];

export function shortenInstruction(text: string, maxLen = 180): string {
  if (text.length <= maxLen) return text;
  const cut = text.slice(0, maxLen);
  const lastSpace = cut.lastIndexOf(" ");
  return (lastSpace > 0 ? cut.slice(0, lastSpace) : cut) + "…";
}

export function pillColorForPrimitive(p: Primitive): string {
  // Pair colors with the paper's palette so cards match figures.
  const map: Record<Primitive, string> = {
    grounding: "bg-coral/10 border-coral/30 text-coral",
    planning: "bg-navy/10 border-navy/30 text-navy",
    state_tracking: "bg-sage/15 border-sage/40 text-sage",
    backtracking: "bg-accent/10 border-accent/30 text-accent",
    patience: "bg-gold/15 border-gold/40 text-[#a8801f]",
    exploration: "bg-navy/10 border-navy/30 text-navy",
    verification: "bg-coral/10 border-coral/30 text-coral",
  };
  return map[p];
}

export function pillColorForDifficulty(d: Difficulty): string {
  const map: Record<Difficulty, string> = {
    easy: "bg-sage/15 border-sage/40 text-sage",
    medium: "bg-gold/15 border-gold/40 text-[#a8801f]",
    hard: "bg-accent/10 border-accent/30 text-accent",
    expert: "bg-coral/15 border-coral/40 text-coral",
    frontier: "bg-navy/15 border-navy/40 text-navy",
  };
  return map[d];
}
