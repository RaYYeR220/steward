import { render, screen } from "@testing-library/react"
import { BillChart } from "./BillChart"

test("shows before and after totals", () => {
  render(<BillChart before={1278} after={856.5} />)
  expect(screen.getByText(/1278/)).toBeInTheDocument()
  expect(screen.getByText(/856.5/)).toBeInTheDocument()
})
