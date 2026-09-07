from pathlib import Path

from synapse import Vault
from synapse.build import build, clean_page, compress, estimate, parse_output, valid_slug
from synapse.config import Config
from synapse.db import connect
from synapse.index import reindex, wikilinks
from synapse.ingest import ingest
from synapse.models import Item, Turn

FIXTURES = Path(__file__).parent / "fixtures"


def test_compress_preserves_owner_and_truncates_others():
    item = Item(
        "chat",
        "chatgpt",
        "Chat",
        "2026-01-01T00:00:00+00:00",
        turns=[Turn("Anshu", "a" * 1_600), Turn("assistant", "b" * 300)],
    )
    compressed = compress(item, "Anshu")
    assert "a" * 1_500 + "…" in compressed
    assert "b" * 240 + "…" in compressed
    assert "a" * 1_501 not in compressed
    assert "b" * 241 not in compressed


def test_page_parser_slug_validator_and_six_page_rail():
    valid_pages = "".join(
        f"===PAGE:page-{number}===\n# Page {number}\nBody\n===END===\n"
        for number in range(7)
    )
    output = parse_output(
        "===PAGE:Invalid_Slug===\n# Bad\nNo\n===END===\n"
        "===PAGE:no-heading===\nBad\n===END===\n"
        + valid_pages
        + "===SUMMARY===\nDone\n===END==="
    )
    assert valid_slug("page-1")
    assert not valid_slug("Invalid_Slug")
    assert len(output.pages) == 6
    assert output.summary == "Done"


def test_wikilink_parser_keeps_relationship_phrase():
    assert wikilinks("## Related\n- [[garden]] — grows food\nSee [[compost]] too") == [
        ("garden", "grows food"),
        ("compost", ""),
    ]


def test_fake_build_writes_rails_provenance_links_and_resumes(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    ingest(vault, FIXTURES / "chatgpt", min_chars=10)
    source_path = next(vault.raw_path.rglob("*.md")).relative_to(vault.path).as_posix()
    calls = []

    def fake_complete(system, user):
        calls.append((system, user))
        return """===PAGE:community-garden===
# Community Garden
Synthetic gardening preferences.

## Facts
- [2024-09-14] The owner wants to grow basil.

## Related
- [[basil]] — planned crop
===END===
===SUMMARY===
Added a garden page.
===END==="""

    result = build(vault, Config(owner="me"), fake_complete, limit=1)
    assert (result.items, result.pages) == (1, 1)
    page = (vault.wiki_path / "community-garden.md").read_text()
    assert source_path in page
    assert len(page) <= 6_000
    assert "## Sources" in page
    assert len(calls) == 1
    assert calls[0][1].count("## PAGE INDEX") == 1
    assert calls[0][1].count("## CANDIDATE PAGES") == 1
    assert calls[0][1].count("## SOURCE") == 1
    with connect(vault.db_path) as connection:
        assert connection.execute("SELECT built_at FROM items").fetchone()[0]
        assert tuple(connection.execute("SELECT * FROM links").fetchone()) == (
            "community-garden",
            "basil",
            "planned crop",
        )
    assert build(vault, Config(), fake_complete).items == 0


def test_nonexistent_model_sources_are_removed(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    content = "# Page\n\n## Sources\n- raw/chatgpt/2026-01/invented.md\n"
    assert "invented.md" not in clean_page(vault, content)


def test_date_placeholders_are_removed_instead_of_invented(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    content = "# Page\n\n## Facts\n- [YYYY-MM-DD] Unsupported date\n- [2026-01-02] Valid\n"
    cleaned = clean_page(vault, content)
    assert "YYYY-MM-DD" not in cleaned
    assert "[2026-01-02] Valid" in cleaned


def test_dry_run_estimate_makes_no_calls(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    ingest(vault, FIXTURES / "chatgpt", min_chars=10)
    quote = estimate(vault, Config(), limit=1, oldest=False)
    assert quote.items == 1
    assert quote.input_tokens > 0
    assert quote.output_tokens == 1_200
    assert quote.dollars > 0


def test_zero_page_result_stays_built_after_database_rebuild(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    ingest(vault, FIXTURES / "chatgpt", min_chars=10)

    result = build(vault, Config(), lambda _system, _user: "===SUMMARY===\nNo facts\n===END===")
    assert (result.items, result.pages) == (1, 0)
    assert vault.status()["unbuilt"] == 0
    assert vault.status()["pages"] == 0

    vault.db_path.unlink()
    reindex(vault.path)
    assert vault.status()["unbuilt"] == 0
