"""첫 화면 — 숫자는 지식베이스에서 그대로 세고, 애니메이션·인라인 SVG 없이 그린다."""
import pathlib

from scanner import kb


def test_kb_stats_come_from_kb():
    import company_view
    s = company_view.kb_stats()
    assert s["industries"] == len(kb.industries()) and s["questions"] >= s["risks"] > 0


def test_hero_is_static_and_lists_every_industry():
    import company_view
    html = company_view.hero_html()
    assert "<svg" not in html and "<animate" not in html          # st.html이 svg를 지우므로 data URI img만
    for v in kb.industries().values():
        assert v["name"] in html
    assert "위험이 보인다" in html


def test_stylesheet_has_no_animation():
    css = (pathlib.Path(__file__).resolve().parent.parent / "assets" / "style.css").read_text(encoding="utf-8")
    assert "@keyframes" not in css and "animation" not in css      # 눈이 피로하다는 피드백 → 움직임 없음
