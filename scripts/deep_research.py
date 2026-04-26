#!/usr/bin/env python
"""CLI entrypoint for deep-research orchestration.

Commands: init, update-ledger, record-scenarios, record-premortem,
finalize-report, list, status, check-sufficiency, rollback
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.deep_research import (
    init_research_project,
    collect_vault_evidence,
    record_scenarios,
    record_premortem,
    finalize_report,
    update_closure,
    resume_research_project,
)
from pipeline.dependency_ledger import (
    add_fact_node,
    update_hypothesis_confidence,
    check_evidence_sufficiency,
    scan_active_research,
    surgical_rollback,
    propagate_confidence,
    research_slug,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep research orchestration")
    sub = parser.add_subparsers(dest="command")

    # init
    init_cmd = sub.add_parser("init", help="Initialize a deep-research project")
    init_cmd.add_argument("--vault", required=True, help="Path to Obsidian vault")
    init_cmd.add_argument("--topic", required=True, help="Research topic")
    init_cmd.add_argument("--hypotheses-json", required=True, help="JSON file with hypothesis cards")

    # update-ledger
    ul_cmd = sub.add_parser("update-ledger", help="Add F node or update H confidence")
    ul_cmd.add_argument("--vault", required=True)
    ul_cmd.add_argument("--topic", required=True)
    ul_cmd.add_argument("--action", required=True, choices=["add-fact", "update-confidence", "propagate"])
    ul_cmd.add_argument("--claim", default="", help="Fact claim (for add-fact)")
    ul_cmd.add_argument("--source", default="", help="Fact source ref (for add-fact)")
    ul_cmd.add_argument("--tier", type=int, default=2, help="Source tier (1/2/3)")
    ul_cmd.add_argument("--hypothesis-id", default="", help="H node ID (for update-confidence)")
    ul_cmd.add_argument("--confidence", type=int, default=0, help="New confidence value")
    ul_cmd.add_argument("--reason", default="", help="Reason for change")
    ul_cmd.add_argument("--depends-on", default="", help="Dependency refs")
    ul_cmd.add_argument("--required-by", default="", help="Required-by refs")

    # record-scenarios
    rs_cmd = sub.add_parser("record-scenarios", help="Record scenario stress test table")
    rs_cmd.add_argument("--vault", required=True)
    rs_cmd.add_argument("--topic", required=True)
    rs_cmd.add_argument("--scenarios-json", required=True, help="JSON file with scenarios")

    # record-premortem
    rp_cmd = sub.add_parser("record-premortem", help="Record pre-mortem failure scenarios")
    rp_cmd.add_argument("--vault", required=True)
    rp_cmd.add_argument("--topic", required=True)
    rp_cmd.add_argument("--premortem-json", required=True, help="JSON file with premortem")

    # finalize-report
    fr_cmd = sub.add_parser("finalize-report", help="Write the final research report")
    fr_cmd.add_argument("--vault", required=True)
    fr_cmd.add_argument("--topic", required=True)
    fr_cmd.add_argument("--report-file", required=True, help="Markdown file with report content")
    fr_cmd.add_argument("--run-closure", action="store_true", help="Also run update_closure")

    # list
    list_cmd = sub.add_parser("list", help="List active research projects")
    list_cmd.add_argument("--vault", required=True)
    list_cmd.add_argument("--json", action="store_true", help="Output as JSON")

    # status
    status_cmd = sub.add_parser("status", help="Show research project status")
    status_cmd.add_argument("--vault", required=True)
    status_cmd.add_argument("--topic", required=True)

    # check-sufficiency
    cs_cmd = sub.add_parser("check-sufficiency", help="Check evidence sufficiency gate")
    cs_cmd.add_argument("--vault", required=True)
    cs_cmd.add_argument("--topic", required=True)

    # rollback
    rb_cmd = sub.add_parser("rollback", help="Surgical rollback of a node")
    rb_cmd.add_argument("--vault", required=True)
    rb_cmd.add_argument("--topic", required=True)
    rb_cmd.add_argument("--node-id", required=True, help="Node ID to roll back")
    rb_cmd.add_argument("--reason", default="", help="Reason for rollback")

    # collect-vault-evidence
    ce_cmd = sub.add_parser("collect-vault-evidence", help="Collect vault evidence for hypotheses")
    ce_cmd.add_argument("--vault", required=True)
    ce_cmd.add_argument("--topic", required=True)
    ce_cmd.add_argument("--claims", nargs="+", required=True, help="Hypothesis claims")

    # resume
    resume_cmd = sub.add_parser("resume", help="Resume an existing research project")
    resume_cmd.add_argument("--vault", required=True)
    resume_cmd.add_argument("--topic", required=True)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    vault = Path(args.vault)

    if args.command == "init":
        h_file = Path(args.hypotheses_json)
        hypotheses = json.loads(h_file.read_text(encoding="utf-8"))
        result = init_research_project(vault, args.topic, hypotheses)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "update-ledger":
        if args.action == "add-fact":
            nid = add_fact_node(
                vault, args.topic,
                claim=args.claim, source=args.source, tier=args.tier,
                depends_on=args.depends_on, required_by=args.required_by,
            )
            print(f"Added {nid}")
        elif args.action == "update-confidence":
            update_hypothesis_confidence(
                vault, args.topic,
                hypothesis_id=args.hypothesis_id,
                new_confidence=args.confidence, reason=args.reason,
            )
            print(f"Updated {args.hypothesis_id} → {args.confidence}%")
        elif args.action == "propagate":
            changed = propagate_confidence(vault, args.topic)
            print(json.dumps(changed, ensure_ascii=False, indent=2))

    elif args.command == "record-scenarios":
        s_file = Path(args.scenarios_json)
        scenarios = json.loads(s_file.read_text(encoding="utf-8"))
        path = record_scenarios(vault, args.topic, scenarios)
        print(f"Written: {path}")

    elif args.command == "record-premortem":
        p_file = Path(args.premortem_json)
        premortem = json.loads(p_file.read_text(encoding="utf-8"))
        path = record_premortem(vault, args.topic, premortem)
        print(f"Written: {path}")

    elif args.command == "finalize-report":
        report_file = Path(args.report_file)
        report_md = report_file.read_text(encoding="utf-8")
        path = finalize_report(vault, args.topic, report_md)
        print(f"Written: {path}")
        if args.run_closure:
            result = update_closure(vault, args.topic)
            print(f"Closure: {len(result['resolved_questions'])} questions resolved, "
                  f"{len(result['stance_updates'])} stance updates")

    elif args.command == "list":
        projects = scan_active_research(vault)
        if args.json:
            print(json.dumps(projects, ensure_ascii=False, indent=2))
        else:
            for p in projects:
                print(f"  [{p['status']}] {p['topic']}  (F:{p['fact_count']} H:{p['hypothesis_count']})")
            if not projects:
                print("  (no active research projects)")

    elif args.command == "status":
        slug = research_slug(args.topic)
        sufficiency = check_evidence_sufficiency(vault, args.topic)
        print(f"Topic: {args.topic}")
        print(f"Slug: {slug}")
        print(f"Gate: {'PASS' if sufficiency['passed'] else 'BLOCKED'}")
        if sufficiency["violations"]:
            for v in sufficiency["violations"]:
                print(f"  - {v}")

    elif args.command == "check-sufficiency":
        result = check_evidence_sufficiency(vault, args.topic)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "rollback":
        affected = surgical_rollback(vault, args.topic, args.node_id, args.reason)
        print(f"Rolled back {args.node_id}, affected: {', '.join(affected)}")

    elif args.command == "collect-vault-evidence":
        evidence = collect_vault_evidence(vault, args.topic, args.claims)
        print(json.dumps(evidence, ensure_ascii=False, indent=2))

    elif args.command == "resume":
        result = resume_research_project(vault, args.topic)
        if "error" in result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())