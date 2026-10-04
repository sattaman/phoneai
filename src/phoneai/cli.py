"""phoneai command line: run the agent, place calls, list call records."""

from phoneai.runtime import bootstrap

bootstrap()

import argparse  # noqa: E402
import asyncio  # noqa: E402
import sys  # noqa: E402
import uuid  # noqa: E402

from phoneai.adapters.contacts_yaml import YamlContacts  # noqa: E402
from phoneai.adapters.records_files import FileCallRecords  # noqa: E402
from phoneai.config import Settings, load_profile, load_scenario  # noqa: E402


def cmd_agent(args: argparse.Namespace) -> None:
    import os

    # Console/browser sessions have no dispatch metadata; these set what they use.
    os.environ["PHONEAI_SCENARIO"] = args.scenario
    os.environ["PHONEAI_PROFILE"] = args.profile
    from phoneai.voice.entry import main as run_agent

    sys.argv = ["phoneai-agent", args.mode, *args.rest]
    run_agent()


def cmd_call(args: argparse.Namespace) -> None:
    from phoneai.adapters.telephony_livekit import CallRequest, dispatch_call

    settings = Settings()
    contacts = YamlContacts(settings.contacts_file)
    try:
        contacts.get(args.contact)
    except KeyError:
        sys.exit(f"Unknown contact {args.contact!r}. Known: {', '.join(contacts.ids()) or 'none'}")
    # Fail fast on bad config before ringing anyone.
    load_scenario(settings.scenarios_dir, args.scenario, settings.owner_name)
    load_profile(settings.profiles_file, args.profile)

    request = CallRequest(
        call_id=uuid.uuid4().hex[:8],
        contact_id=args.contact,
        scenario=args.scenario,
        profile=args.profile,
    )
    asyncio.run(dispatch_call(request))
    print(f"Call {request.call_id} dispatched to {args.contact} ({args.scenario}).")


def cmd_calls(args: argparse.Namespace) -> None:
    records = FileCallRecords(Settings().calls_dir).recent(args.limit)
    if not records:
        print("No calls yet.")
    for r in records:
        arr = ""
        if r.arrangement:
            a = r.arrangement
            arr = f"  {a.day:%a %d %b} {a.start:%H:%M} @ {a.place}"
        print(
            f"{r.started_at:%Y-%m-%d %H:%M}  {r.call_id}  {r.contact_id or '-':10} "
            f"{r.scenario:20} {r.outcome.value:12}{arr}"
        )


def cmd_eval(args: argparse.Namespace) -> None:
    """Run the scenario evals once per model (one LangSmith experiment each), then write
    a comparison table."""
    import json
    import os
    import subprocess
    from datetime import datetime
    from pathlib import Path

    import httpx

    from phoneai.evals import load_cases, read_rows, render_report

    expected_rows = len(load_cases(Path("evals/cases.yaml"))) * args.samples
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    results = Path("evals/results") / f"{stamp}.jsonl"
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    for model in models:
        print(f"== {model}")
        env = {
            **os.environ,
            "EVAL_MODEL": model,
            "EVAL_SAMPLES": str(args.samples),
            "EVAL_RESULTS": str(results),
            "LANGSMITH_PROJECT": "phoneai-tests",
            "LANGSMITH_TEST_SUITE": "phoneai-gym-evals",
            "LANGSMITH_EXPERIMENT": f"{model.split('/')[-1]}-{stamp}",
            "LANGSMITH_EXPERIMENT_METADATA": json.dumps(
                {"model": model, "samples": args.samples, "reasoning": args.reasoning or "-"}
            ),
            "EVAL_REASONING_EFFORT": args.reasoning or "",
        }
        # pytest exits 1 when checks fail (expected); 2+ means the run itself broke.
        code = subprocess.run(["pytest", "-m", "eval", "-q", "tests/evals"], env=env).returncode
        if code > 1:
            print(f"!! eval run for {model} errored (pytest exit {code})")

    rows = read_rows(results) if results.exists() else []
    incomplete = {m: n for m in models if (n := sum(r.model == m for r in rows)) != expected_rows}
    if not rows:
        sys.exit("No eval results recorded; nothing to report.")

    catalogue = httpx.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
    prices = {
        m["id"]: (float(m["pricing"]["prompt"]), float(m["pricing"]["completion"]))
        for m in catalogue
    }
    report = render_report(rows, prices)
    if incomplete:
        report += (
            "\n**Incomplete runs** (rows recorded / expected): "
            + ", ".join(f"`{m}` {n}/{expected_rows}" for m, n in incomplete.items())
            + "\n"
        )
    header = (
        f"# Model comparison: book_gym_session\n\n"
        f"Run {datetime.now():%Y-%m-%d %H:%M}; {args.samples} sample(s) per case; "
        f"cases in `evals/cases.yaml`; judges: LiveKit task_completion + tool_use "
        f"({os.getenv('EVAL_JUDGE_MODEL', 'google/gemini-2.5-flash')}). Cost is the agent "
        f"LLM only (OpenRouter list prices), excluding STT/TTS and judges.\n\n"
    )
    Path(args.out).write_text(header + report)
    print(report)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="phoneai")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("agent", help="run the voice agent worker (dev | start | console)")
    p.add_argument("mode", choices=["dev", "start", "console"])
    p.add_argument("--scenario", default="book_gym_session", help="for console/browser sessions")
    p.add_argument("--profile", default="uk_default", help="for console/browser sessions")
    p.set_defaults(func=cmd_agent)

    p = sub.add_parser("call", help="have the running agent call a contact")
    p.add_argument("contact", help="contact id from contacts.local.yaml")
    p.add_argument("--scenario", default="book_gym_session")
    p.add_argument("--profile", default="uk_default")
    p.set_defaults(func=cmd_call)

    p = sub.add_parser("calls", help="list recent call records")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_calls)

    p = sub.add_parser("eval", help="compare models on the scenario evals (costs money)")
    p.add_argument("--models", default="google/gemini-2.5-flash-lite")
    p.add_argument("--samples", type=int, default=2)
    p.add_argument("--out", default="docs/evals.md")
    p.add_argument("--reasoning", default=None, help="reasoning effort for reasoning models")
    p.set_defaults(func=cmd_eval)

    # Unknown options after `agent <mode>` are passed through to LiveKit's CLI.
    args, extra = parser.parse_known_args(argv)
    if extra and args.command != "agent":
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    args.rest = extra
    args.func(args)


if __name__ == "__main__":
    main()
