export interface Resource {
  id: string; type: string; name: string; status: string; region: string
  monthly_cost_usd: number; cost_source: string; tags: Record<string, string>
  age_days: number; attached_to: string | null
}
export interface Finding {
  kind: string; resource_id: string; evidence: string
  monthly_saving_usd: number; action_type: string; source: string
}
export interface Decision {
  resource_id: string; action_type: string; monthly_saving_usd: number
  blast_radius: number; blast_reasons: string[]; allowed: boolean
  reasons: string[]; source: string
}
export interface ScanResponse {
  resources: Resource[]; findings: Finding[]
  total_monthly_usd: number; potential_saving_usd: number; warnings: string[]
}
export interface PlanResponse {
  decisions: Decision[]; allowed_saving_usd: number; blocked_saving_usd: number
}
export interface AgentResponse {
  narrative: string; findings: Finding[]; decisions: Decision[]
  allowed_saving_usd: number; blocked_saving_usd: number
  prompt_tokens: number; completion_tokens: number
  degraded: boolean; degraded_reason: string | null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- raw agent transcript events are structurally dynamic
  transcript: any[]
}
