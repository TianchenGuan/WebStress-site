export type Primitive =
  | "grounding"
  | "planning"
  | "state_tracking"
  | "backtracking"
  | "patience"
  | "exploration"
  | "verification";

export type Environment =
  | "gmail"
  | "amazon"
  | "reddit"
  | "robinhood"
  | "booking"
  | "lms"
  | "patient_portal";

export type Difficulty = "easy" | "medium" | "hard" | "expert" | "frontier";

export type InjectionLayer = "seed" | "server" | "network" | "client";

export interface TaskEntry {
  task_id: string;
  env_id: Environment;
  title: string;
  public_instruction: string;
  difficulty: Difficulty;
  primary_primitive: Primitive;
  secondary_primitives: Primitive[];
  expected_steps: number;
  time_limit_seconds: number;
  // Intervention pair, if one is published.
  has_intervention: boolean;
  variant_id: string | null;
  target_primitive: Primitive | null;
  intervention_layer: InjectionLayer | null;
  intervention_family: string | null;
  intervention_summary_public: string | null;
  // Human study flags.
  human140: boolean;
  duplicate_audit: boolean;
  // Where this entry came from (relative to the public benchmark repo root).
  source_path: string;
}

export interface PrimitiveCard {
  primitive: Primitive;
  label: string;
  definition: string;
  what_it_targets: string;
  typical_families: string[];
  example_task_id: string | null;
  example_intervention_summary: string | null;
  task_count: number;
  intervention_count: number;
}

export interface EnvironmentCard {
  env_id: Environment;
  label: string;
  domain: string;
  description: string;
  task_count: number;
  difficulty_counts: Record<Difficulty, number>;
  primitive_counts: Partial<Record<Primitive, number>>;
}

export interface AgentRow {
  model: string;
  harness: "text" | "vision";
  total_clean_pass: number;
  total_iv_pass: number;
  total_delta_p: number;
  // Per-primitive intervention pass + delta, in pp. Optional.
  per_primitive?: Partial<Record<Primitive, { iv_pass: number; delta_p: number }>>;
}

export interface ResultsSummary {
  // Headline numbers cited in the paper.
  headline: {
    text_drop_range_pp: [number, number];
    text_belief_failure_share_pct: number;
    vision_action_failure_share_pct: number;
    warm_human_drop_pp: number;
    cold_human_drop_pp: number;
  };
  agents: AgentRow[];
  // Rule-based classifier failure-mode shares (Table 4).
  failure_class_by_harness: {
    text: { belief_pct: number; action_pct: number; overreach_pct: number; n: number };
    vision: { belief_pct: number; action_pct: number; overreach_pct: number; n: number };
  };
  // Optional figure references that the /results page renders.
  figures: { src: string; caption: string }[];
}
