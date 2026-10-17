"""2026-10-17 に保存した実際のページ・カレンダーで、読み取り結果を確かめる。"""

import datetime as dt
from pathlib import Path

from skate.common import CLOSED, OPEN, PLANNED, UNPUBLISHED, CONFIRMED
from skate.sources import calendars, html_pages, rules

FX = Path(__file__).parent / "fixtures"
TODAY = dt.date(2026, 10, 17)
END = dt.date(2026, 11, 30)


def b(name):
    return (FX / name).read_bytes()


def t(name):
    return (FX / name).read_text(encoding="utf-8")


def sess(rec):
    return [(s.rink, s.start, s.end) for s in sorted(rec.sessions, key=lambda s: (s.rink != "main", s.start))]


def test_maorink():
    r = calendars.parse_maorink(b("maorink_b.ics"), b("maorink_a.ics"), TODAY, END, "u")
    assert sess(r[TODAY]) == [("main", "11:00", "17:30"), ("sub", "11:45", "16:45")]
    assert ("sub", "19:00", "21:00") in sess(r[dt.date(2026, 10, 20)])
    assert r[dt.date(2026, 10, 26)].status == CLOSED


def test_tatsumi():
    r = calendars.parse_tatsumi(b("tatsumi.ics"), TODAY, END, "u")
    assert r[dt.date(2026, 10, 18)].status == CLOSED
    assert r[dt.date(2026, 10, 19)].status == CLOSED
    d20 = r[dt.date(2026, 10, 20)]
    assert d20.status == OPEN and sess(d20) == [("sub", "11:30", "14:00")]
    assert r[dt.date(2026, 11, 5)].status == UNPUBLISHED
    assert r[dt.date(2026, 11, 16)].status == CLOSED


def test_saitama():
    r = calendars.parse_saitama(b("saitama_b.ics"), TODAY, END, "u")
    assert sess(r[TODAY]) == [("main", "10:00", "16:45"), ("sub", "10:00", "17:45")]
    assert sess(r[dt.date(2026, 10, 20)]) == [("sub", "10:00", "17:45")]
    assert ("main", "16:30", "17:45") in sess(r[dt.date(2026, 10, 19)])


def test_daido():
    r = html_pages.parse_daido(t("daido.html"), TODAY, END, "u", TODAY)
    assert r[TODAY].status == CLOSED
    assert sess(r[dt.date(2026, 10, 19)]) == [("main", "14:30", "18:00")]
    assert r[dt.date(2026, 11, 1)].status == UNPUBLISHED


def test_edogawa():
    r = html_pages.parse_edogawa(t("edogawa.html"), TODAY, END, "u", TODAY)
    assert sess(r[TODAY]) == [("main", "10:00", "18:00")]
    assert r[dt.date(2026, 10, 20)].status == CLOSED
    assert sess(r[dt.date(2026, 11, 2)]) == [("main", "9:00", "18:00")]


def test_jingu():
    r = html_pages.parse_jingu(t("jingu.html"), TODAY, END, "u", TODAY)
    assert r[TODAY].basis == CONFIRMED and sess(r[TODAY]) == [("main", "10:00", "18:00")]
    d19 = r[dt.date(2026, 10, 19)]
    assert d19.basis == PLANNED and sess(d19) == [("main", "13:00", "18:00")]


def test_higashiyamato():
    r = html_pages.parse_higashiyamato(t("higashiyamato.html"), TODAY, END, "u", TODAY)
    assert sess(r[TODAY]) == [("main", "13:30", "15:30")]


def test_kirifuri_and_rules():
    manual = rules.read_manual_sheet(t("manual_sheet.csv"))
    r = rules.kirifuri(TODAY, END, "u", manual)
    assert r[dt.date(2026, 10, 24)].basis == CONFIRMED
    assert r[dt.date(2026, 10, 25)].status == CLOSED
    assert r[dt.date(2026, 10, 26)].basis == PLANNED
    u = rules.utsunomiya(TODAY, END, "u")
    assert u[dt.date(2026, 10, 21)].status == CLOSED          # 水曜休場
    assert sess(u[dt.date(2026, 10, 19)]) == [("main", "13:00", "19:00")]
    assert sess(u[TODAY]) == [("main", "9:00", "17:00")]
