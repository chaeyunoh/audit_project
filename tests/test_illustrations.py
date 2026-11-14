"""st.html은 HTML을 정화하면서 인라인 <svg>를 지운다 → 그림 칸이 빈칸이 된다.
화면에 넣는 일러스트는 반드시 data URI <img>로 나가야 한다."""
import base64
import re

import illustrations as art


def test_img_wraps_valid_svg_as_data_uri():
    out = art.img("build", 72, label='크레인 <x>')
    assert out.startswith("<img ") and "<svg" not in out
    data = re.search(r'src="data:image/svg\+xml;base64,([^"]+)"', out).group(1)
    svg = base64.b64decode(data).decode("utf-8")
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg     # 단독 이미지로 그려지려면 필요
    assert "<script" not in svg
    assert 'alt="크레인 &lt;x&gt;"' in out


def test_ui_html_never_embeds_inline_svg():
    """st.html로 나가는 화면 코드에서 인라인 svg 호출이 다시 생기지 않도록 막는다."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = [p.name for p in [*root.glob("*.py"), *root.glob("app_pages/*.py")]
                 if p.name != "illustrations.py" and re.search(r"art\.(industry_)?svg\(", p.read_text(encoding="utf-8"))]
    assert offenders == [], f"st.html에 인라인 SVG를 넣는 파일: {offenders} — art.img()/art.industry_img()를 쓰세요"
