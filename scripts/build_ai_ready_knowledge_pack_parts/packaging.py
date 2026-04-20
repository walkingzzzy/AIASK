

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an AI-ready knowledge pack from mixed research materials.")
    parser.add_argument("--source", required=True, help="Source directory containing raw materials.")
    parser.add_argument("--output", help="Output directory. Defaults to <source>/ai_ready.")
    parser.add_argument("--asset-code", default="SC", help="Compatibility code written to metadata/stock_code.")
    parser.add_argument("--asset-name", default="原油", help="Human-friendly asset name written to summaries.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        raise SystemExit(f"source directory does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise SystemExit(f"source path is not a directory: {source_dir}")
    output_dir = Path(args.output).expanduser().resolve() if args.output else source_dir / "ai_ready"
    builder = KnowledgePackBuilder(
        source_dir=source_dir,
        output_dir=output_dir,
        asset_code=str(args.asset_code).strip() or "SC",
        asset_name=str(args.asset_name).strip() or "原油",
    )
    builder.run()


if __name__ == "__main__":
    main()
