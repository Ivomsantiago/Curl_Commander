import sys


def main() -> None:
    from curlcommander.cli.arg_parser import SUBCOMMANDS, build_request_parser, build_subcommand_parser
    from curlcommander.config import migrate_legacy

    # One-time migration of a legacy ~/.curlcommander to the OS data dir (F1.2).
    migrate_legacy()

    # Detect subcommand before argparse can misinterpret a URL as one
    positionals = [a for a in sys.argv[1:] if not a.startswith("-")]
    is_subcommand = bool(positionals) and positionals[0] in SUBCOMMANDS

    if "--gui" in sys.argv:
        from curlcommander.gui.app import CurlCommanderApp

        CurlCommanderApp().run()
        return

    if is_subcommand:
        args = build_subcommand_parser().parse_args()
    else:
        args = build_request_parser().parse_args()
        args.subcommand = None

    from curlcommander.cli.runner import run_cli

    sys.exit(run_cli(args))


if __name__ == "__main__":
    main()
