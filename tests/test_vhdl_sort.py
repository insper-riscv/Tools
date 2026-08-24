from pathlib import Path

from riscv_tools.vhdl_sort import topo_sort


def test_topo_sort_orders_entity_dependency(tmp_path: Path) -> None:
    sub = tmp_path / "sub.vhd"
    sub.write_text("entity sub is\nend entity;\n")
    top = tmp_path / "top.vhd"
    top.write_text(
        "entity top is\nend entity;\n"
        "architecture rtl of top is\nbegin\n"
        "  u: entity work.sub port map ();\n"
        "end architecture;\n"
    )

    ordered = topo_sort([top, sub])
    assert ordered.index(sub) < ordered.index(top)


def test_topo_sort_orders_package_dependency(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg.vhd"
    pkg.write_text("package pkg_types is\nend package;\n")
    consumer = tmp_path / "consumer.vhd"
    consumer.write_text("use work.pkg_types.all;\nentity consumer is\nend entity;\n")

    ordered = topo_sort([consumer, pkg])
    assert ordered.index(pkg) < ordered.index(consumer)


def test_topo_sort_ignores_package_body(tmp_path: Path) -> None:
    # "package body X" must not register a design unit named "body".
    pkg = tmp_path / "pkg.vhd"
    pkg.write_text(
        "package pkg_types is\nend package;\n\n"
        "package body pkg_types is\nend package body;\n"
    )

    ordered = topo_sort([pkg])
    assert ordered == [pkg]


def test_topo_sort_is_deterministic_for_unrelated_files(tmp_path: Path) -> None:
    a = tmp_path / "a.vhd"
    a.write_text("entity a is\nend entity;\n")
    b = tmp_path / "b.vhd"
    b.write_text("entity b is\nend entity;\n")

    assert topo_sort([b, a]) == topo_sort([a, b]) == sorted([a, b])


def test_topo_sort_breaks_cycles_without_raising(tmp_path: Path) -> None:
    a = tmp_path / "a.vhd"
    a.write_text(
        "entity a is\nend entity;\n"
        "architecture x of a is begin u: entity work.b port map(); end architecture;\n"
    )
    b = tmp_path / "b.vhd"
    b.write_text(
        "entity b is\nend entity;\n"
        "architecture x of b is begin u: entity work.a port map(); end architecture;\n"
    )

    ordered = topo_sort([a, b])
    assert set(ordered) == {a, b}


def test_topo_sort_skips_unreadable_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.vhd"
    present = tmp_path / "present.vhd"
    present.write_text("entity present is\nend entity;\n")

    ordered = topo_sort([missing, present])
    assert set(ordered) == {missing, present}


def test_topo_sort_ignores_dependency_outside_input_set(tmp_path: Path) -> None:
    # A dependency on a unit declared in a file not passed to
    # topo_sort (e.g. a vendor IP core) shouldn't raise or pull it in.
    only_file = tmp_path / "top.vhd"
    only_file.write_text(
        "entity top is\nend entity;\n"
        "architecture rtl of top is\nbegin\n"
        "  u: entity work.vendor_ip port map ();\n"
        "end architecture;\n"
    )

    assert topo_sort([only_file]) == [only_file]
