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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="phoneai")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("agent", help="run the voice agent worker (dev | start | console)")
    p.add_argument("mode", choices=["dev", "start", "console"])
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_agent)

    p = sub.add_parser("call", help="have the running agent call a contact")
    p.add_argument("contact", help="contact id from contacts.local.yaml")
    p.add_argument("--scenario", default="book_gym_session")
    p.add_argument("--profile", default="uk_default")
    p.set_defaults(func=cmd_call)

    p = sub.add_parser("calls", help="list recent call records")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_calls)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
