import pytest

from app.services.catalog import ImportRejected, parse_import_csv

SUPPLIERS = {"Supplier A": 1, "Supplier B": 2}
HEADER = "sku,supplier,url,selection_hint\n"


def test_valid_rows_become_import_rows_with_spreadsheet_row_numbers() -> None:
    rows, errors = parse_import_csv(
        HEADER + "SKU-1,Supplier A,https://a.example/p/1,Black / L\n"
        "SKU-2,Supplier B,http://b.example/2,\n",
        SUPPLIERS,
    )
    assert errors == []
    assert [(r.sku, r.supplier_id, r.url, r.selection_hint, r.row_number) for r in rows] == [
        ("SKU-1", 1, "https://a.example/p/1", "Black / L", 2),
        ("SKU-2", 2, "http://b.example/2", "", 3),
    ]


def test_selection_hint_column_is_optional() -> None:
    text = "sku,supplier,url\nS,Supplier A,https://a.example/1\n"
    rows, errors = parse_import_csv(text, SUPPLIERS)
    assert errors == [] and rows[0].selection_hint == ""


def test_whitespace_is_trimmed_and_blank_lines_ignored() -> None:
    rows, _ = parse_import_csv(
        HEADER + "\n  S1 , Supplier A , https://a.example/1 ,\n\n", SUPPLIERS
    )
    assert [(r.sku, r.url) for r in rows] == [("S1", "https://a.example/1")]


@pytest.mark.parametrize(
    ("line", "message"),
    [
        (",Supplier A,https://a.example/1,", "SKU"),
        ("S1,Nobody,https://a.example/1,", "Supplier"),
        ("S1,Supplier A,not-a-url,", "URL"),
        ("S1,Supplier A,javascript:alert(1),", "URL"),
        ("S1,Supplier A,,", "URL"),
    ],
)
def test_bad_rows_are_reported_and_the_good_ones_kept(line: str, message: str) -> None:
    rows, errors = parse_import_csv(
        HEADER + line + "\nS2,Supplier A,https://a.example/2,\n", SUPPLIERS
    )
    assert [r.sku for r in rows] == ["S2"]
    assert len(errors) == 1 and errors[0].row == 2 and message in errors[0].message


def test_a_row_with_too_few_columns_is_an_error() -> None:
    rows, errors = parse_import_csv(HEADER + "S1,Supplier A\n", SUPPLIERS)
    assert rows == [] and errors[0].row == 2


@pytest.mark.parametrize("header", ["sku,url\n", "a,b,c\n", "", "supplier,url,sku2\n"])
def test_a_missing_required_column_rejects_the_whole_file(header: str) -> None:
    with pytest.raises(ImportRejected):
        parse_import_csv(header, SUPPLIERS)


def test_header_names_are_case_insensitive_and_order_free() -> None:
    text = "URL,SKU,Supplier\nhttps://a.example/1,S1,Supplier A\n"
    rows, errors = parse_import_csv(text, SUPPLIERS)
    assert errors == [] and rows[0].sku == "S1"


def test_a_utf8_bom_from_excel_is_ignored() -> None:
    rows, _ = parse_import_csv("﻿sku,supplier,url\nS1,Supplier A,https://a.example/1\n", SUPPLIERS)
    assert len(rows) == 1


def test_too_many_rows_are_rejected() -> None:
    body = "sku,supplier,url\n" + "S,Supplier A,https://a.example/1\n" * 10_001
    with pytest.raises(ImportRejected, match="10000"):
        parse_import_csv(body, SUPPLIERS)
