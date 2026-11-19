from ats_resume_check import FAIL, PASS, WARN, check_dates, check_fonts, check_headings, check_text, check_word_spaces

GOOD = """Jordan Sample
jordan@example.com · (555) 010-2030 · Boston, MA
Experience
Content Lead, Example Co. Mar 2020 – Present
Led the content team and shipped a quarterly report read by buyers.
Education
B.A., English, Example University
Skills
Writing, editing, video
""" + "Built guides, films and events for marketing technology buyers. " * 10


def levels(findings):
    return {f.check: f.level for f in findings}


def test_good_resume_passes():
    assert set(levels(check_text(GOOD)).values()) == {PASS}


def test_image_pdf_fails_early():
    out = check_text("Jordan Sample")
    assert [f.level for f in out] == [FAIL]


def test_words_run_together():
    text = " ".join(["Ledthecontentteamandshippedaquarterlyreport"] * 10 + ["ok"] * 50)
    assert check_word_spaces(text).level == FAIL


def test_year_only_dates_warn():
    assert check_dates("Content Lead 2019 – 2023\nWriter 2015 - 2019").level == WARN


def test_month_dates_pass():
    assert check_dates("Content Lead Mar 2019 – Jun 2023").level == PASS


def test_numbered_headings_warn():
    assert check_headings("01 Experience\n02 Education\n03 Skills").level == WARN


def test_type3_font_warns():
    assert check_fonts([("ABCDEF+Inter", "Type 3")]).level == WARN
    assert check_fonts([("ABCDEF+Inter", "TrueType")]).level == PASS
