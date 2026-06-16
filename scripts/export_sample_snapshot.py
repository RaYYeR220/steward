"""Write dashboard/public/sample-snapshot.json from the mock demo (static fallback)."""
import json
from pathlib import Path

from steward.demo_seed import seed_demo
from steward.policy import Policy
from steward.snapshot import plan_snapshot, scan_snapshot

scan = scan_snapshot(seed_demo())
plan = plan_snapshot(seed_demo(), Policy(max_blast_radius=4, allow_irreversible=True))
agent = {
    "narrative": "Reviewed 11 resources; the detectors already cover the waste here.",
    "findings": scan["findings"],
    "decisions": plan["decisions"],
    "allowed_saving_usd": plan["allowed_saving_usd"],
    "blocked_saving_usd": plan["blocked_saving_usd"],
    "prompt_tokens": 0, "completion_tokens": 0,
    "degraded": False, "degraded_reason": None, "transcript": [],
}
out = Path("dashboard/public/sample-snapshot.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"scan": scan, "plan": plan, "agent": agent}, indent=2), encoding="utf-8")
print(f"wrote {out}")
