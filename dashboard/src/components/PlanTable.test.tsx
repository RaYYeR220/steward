import { render, screen } from "@testing-library/react"
import { PlanTable } from "./PlanTable"
import type { Decision } from "../types"

const decisions: Decision[] = [
  { resource_id: "eip-1", action_type: "release_eip", monthly_saving_usd: 9,
    blast_radius: 1, blast_reasons: [], allowed: true, reasons: [], source: "detector" },
  { resource_id: "i-prod", action_type: "resize_ecs", monthly_saving_usd: 140,
    blast_radius: 4, blast_reasons: [], allowed: false,
    reasons: ["protected by tag env=production"], source: "detector" },
]

test("renders allow and block badges with reasons", () => {
  render(<PlanTable decisions={decisions} />)
  expect(screen.getByText("eip-1")).toBeInTheDocument()
  expect(screen.getByText(/ALLOW/i)).toBeInTheDocument()
  expect(screen.getByText(/BLOCK/i)).toBeInTheDocument()
  expect(screen.getByText(/env=production/)).toBeInTheDocument()
})
