from datetime import UTC, datetime, timedelta

from orbital_cli import output
from orbital_cli.output import Column, col


def test_default_format_follows_tty(monkeypatch):
    monkeypatch.setattr(output, "stdout_is_tty", lambda: True)
    assert output.default_format(None) == "table"
    monkeypatch.setattr(output, "stdout_is_tty", lambda: False)
    assert output.default_format(None) == "json"
    assert output.default_format("table") == "table"


def test_render_table_aligns_and_formats_cells():
    rows = [{"a": "x", "b": None, "c": ["p", "q"]}, {"a": "longer", "b": True, "c": []}]
    text = output.render_table(rows, [col("A", "a"), col("B", "b"), col("C", "c")])
    assert text.splitlines() == [
        "A       B    C",
        "x       -    p,q",
        "longer  yes  -",
    ]


def test_render_fields_accepts_callables():
    text = output.render_fields({"x": 1}, [("value", "x"), ("double", lambda o: o["x"] * 2)])
    assert text.splitlines() == ["value   1", "double  2"]


def test_ago():
    now = datetime.now(UTC)
    assert output.ago(None) == "-"
    assert output.ago((now - timedelta(minutes=3, seconds=5)).isoformat()) == "3m ago"
    assert output.ago((now - timedelta(days=2)).isoformat()) == "2d ago"
    naive = (now - timedelta(hours=5)).replace(tzinfo=None).isoformat()
    assert output.ago(naive) == "5h ago"
    assert output.ago("garbage") == "garbage"
    assert output.ago((now + timedelta(minutes=1)).isoformat()) == "just now"


def test_emit_formats(capsys):
    rows = [{"id": "1", "slug": "a"}, {"id": "2", "slug": "b"}]
    output.emit(rows, "name", name_key="slug")
    assert capsys.readouterr().out == "a\nb\n"
    output.emit(rows, "json")
    assert '"slug": "a"' in capsys.readouterr().out
    output.emit([], "table", columns=[Column("X", lambda r: r)], empty="nothing")
    captured = capsys.readouterr()
    assert captured.out == "" and "nothing" in captured.err
    output.emit(rows, "table")  # columns inferred from keys
    assert capsys.readouterr().out.splitlines()[0].split() == ["ID", "SLUG"]


def test_write_text_adds_trailing_newline(capsys):
    output.write_text("a\nb")
    output.write_text("")
    assert capsys.readouterr().out == "a\nb\n"
