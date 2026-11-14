"""가치사슬 단계·산업 일러스트 (인라인 SVG, 64×64).

선은 잉크색, 면은 하늘·크림·파랑 세 가지로만 칠한다. 외부 파일·스크립트 없음.
지식베이스 stage_info.icon 값이 아래 키와 연결된다.
"""
from __future__ import annotations

import base64
from html import escape

INK, SKY, CREAM, BLUE, PAPER = "#0B0B0C", "#A9CFF5", "#F3EEDD", "#2F7FE0", "#FFFFFF"
_S = f'fill="none" stroke="{INK}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'

_ICONS: dict[str, str] = {
    # 입찰: 서류 + 파란 도장
    "bid": f'''<rect x="14" y="8" width="30" height="40" rx="3" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
<path d="M20 18h18M20 25h18M20 32h10" {_S}/><circle cx="42" cy="44" r="10" fill="{BLUE}" stroke="{INK}" stroke-width="2"/>
<path d="M37.5 44l3 3 5.5-6" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>''',
    # 계약: 서류 + 서명 + 펜
    "contract": f'''<rect x="10" y="10" width="32" height="42" rx="3" fill="{CREAM}" stroke="{INK}" stroke-width="2"/>
<path d="M16 20h20M16 27h20M16 34h12" {_S}/><path d="M16 44c3-4 5 3 8-1s4 2 7-1" {_S}/>
<path d="M44 46l12-24 4 2-12 24-5 2z" fill="{SKY}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>''',
    # 착공: 흙더미 + 삽
    "groundbreak": f'''<path d="M6 52c8-12 18-14 26-14s18 4 26 14z" fill="{CREAM}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<path d="M40 8l-8 30" {_S}/><path d="M36 6h10" {_S}/><path d="M27 36l10 3-3 9-9-3z" fill="{BLUE}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>''',
    # 공사 진행: 크레인 + 건물
    "build": f'''<path d="M14 56V10M14 10h40M14 16l8-6M22 10v8" {_S}/><path d="M46 10v10" {_S}/>
<rect x="41" y="20" width="10" height="7" fill="{BLUE}" stroke="{INK}" stroke-width="2"/>
<rect x="26" y="34" width="26" height="22" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<path d="M32 40h4M42 40h4M32 47h4M42 47h4" {_S}/><path d="M8 56h50" {_S}/>''',
    # 기성 청구: 영수증 + ₩
    "invoice": f'''<path d="M16 6h32v50l-5-3-5 3-5-3-6 3-5-3-6 3z" fill="{PAPER}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<circle cx="32" cy="24" r="10" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<path d="M27 19l3 10 2-6 2 6 3-10M26 24h12" fill="none" stroke="{INK}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M22 40h20M22 46h12" {_S}/>''',
    # 준공: 완성 건물 + 깃발
    "complete": f'''<rect x="14" y="22" width="28" height="34" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<path d="M20 30h4M32 30h4M20 38h4M32 38h4" {_S}/><rect x="25" y="46" width="6" height="10" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
<path d="M42 56h12V36H42" fill="{CREAM}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<path d="M28 22V6" {_S}/><path d="M28 6l12 4-12 4z" fill="{BLUE}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>''',
    # 하자보수: 렌치
    "repair": f'''<path d="M44 8a10 10 0 0 0-9 14L12 45a5 5 0 0 0 7 7l23-23a10 10 0 0 0 14-9l-7 3-5-5 3-7z" fill="{SKY}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<circle cx="16" cy="48" r="2" fill="{INK}"/><path d="M6 58h20" {_S}/>''',
    # 설계: 칩 도면 + 연필
    "design": f'''<rect x="8" y="8" width="40" height="40" rx="2" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<path d="M8 18h40M8 28h40M8 38h40M18 8v40M28 8v40M38 8v40" fill="none" stroke="#fff" stroke-width="1.5"/>
<rect x="18" y="18" width="20" height="20" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
<path d="M40 58l16-16 4 4-16 16h-4z" fill="{BLUE}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>''',
    # 웨이퍼: 원판 + 격자
    "wafer": f'''<circle cx="32" cy="32" r="24" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<path d="M14 24h36M10 32h44M14 40h36M24 12v40M32 8v48M40 12v40" fill="none" stroke="#fff" stroke-width="1.6"/>
<rect x="32" y="24" width="8" height="8" fill="{BLUE}"/><path d="M27 55h10" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>''',
    # 패키징: 다리 달린 칩
    "package": f'''<rect x="16" y="16" width="32" height="32" rx="3" fill="{INK}"/>
<path d="M22 10v6M30 10v6M38 10v6M22 48v6M30 48v6M38 48v6M10 24h6M10 32h6M10 40h6M48 24h6M48 32h6M48 40h6" {_S}/>
<circle cx="23" cy="23" r="2" fill="{SKY}"/><rect x="26" y="28" width="14" height="10" rx="1" fill="{BLUE}"/>''',
    # 테스트: 칩 + 돋보기
    "test": f'''<rect x="8" y="12" width="30" height="30" rx="3" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<path d="M14 6v6M23 6v6M32 6v6M14 42v6M23 42v6M32 42v6" {_S}/>
<circle cx="40" cy="38" r="11" fill="{PAPER}" stroke="{INK}" stroke-width="2.4"/>
<path d="M35 38l3.5 3.5 6.5-7" fill="none" stroke="{BLUE}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M48 46l8 8" stroke="{INK}" stroke-width="3.4" stroke-linecap="round"/>''',
    # 판매: 배송 트럭
    "sell": f'''<rect x="4" y="18" width="34" height="24" rx="2" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<path d="M38 26h10l8 9v7H38z" fill="{CREAM}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<circle cx="15" cy="46" r="5" fill="{PAPER}" stroke="{INK}" stroke-width="2"/><circle cx="46" cy="46" r="5" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
<path d="M12 28h14M12 34h8" stroke="{BLUE}" stroke-width="2.4" stroke-linecap="round"/>''',
    # 브랜드: 별 달린 태그
    "brand": f'''<path d="M8 30L30 8h20v20L28 50z" fill="{CREAM}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<circle cx="42" cy="16" r="3" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
<path d="M29 22l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z" fill="{BLUE}" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>''',
    # 개점 지원: 차양 있는 점포
    "store": f'''<rect x="10" y="26" width="44" height="30" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
<path d="M6 26l6-14h40l6 14z" fill="{SKY}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<path d="M6 26c0 4 7 4 7 0 0 4 7 4 7 0 0 4 8 4 8 0 0 4 8 4 8 0 0 4 7 4 7 0 0 4 7 4 7 0" fill="{BLUE}" stroke="{INK}" stroke-width="2"/>
<rect x="16" y="38" width="10" height="18" fill="{CREAM}" stroke="{INK}" stroke-width="2"/><rect x="32" y="38" width="16" height="10" fill="{SKY}" stroke="{INK}" stroke-width="2"/>''',
    # 물류: 상자 + 트럭
    "truck": f'''<rect x="4" y="18" width="34" height="24" rx="2" fill="{CREAM}" stroke="{INK}" stroke-width="2"/>
<path d="M38 26h10l8 9v7H38z" fill="{SKY}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<circle cx="15" cy="46" r="5" fill="{PAPER}" stroke="{INK}" stroke-width="2"/><circle cx="46" cy="46" r="5" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
<rect x="12" y="23" width="12" height="12" fill="{BLUE}" stroke="{INK}" stroke-width="1.6"/><path d="M18 23v5" stroke="#fff" stroke-width="1.6"/>''',
    # 로열티: 동전 더미
    "royalty": f'''<ellipse cx="26" cy="46" rx="16" ry="6" fill="{CREAM}" stroke="{INK}" stroke-width="2"/>
<path d="M10 46v-8c0 3 7 6 16 6s16-3 16-6v8" fill="{CREAM}" stroke="{INK}" stroke-width="2"/>
<ellipse cx="26" cy="38" rx="16" ry="6" fill="{CREAM}" stroke="{INK}" stroke-width="2"/>
<circle cx="44" cy="22" r="13" fill="{BLUE}" stroke="{INK}" stroke-width="2"/>
<path d="M38.5 17l2.5 10 3-7 3 7 2.5-10M37.5 22h13" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>''',
    # 상품권: 카드 두 장 + 리본
    "giftcard": f'''<rect x="12" y="10" width="40" height="26" rx="3" fill="{CREAM}" stroke="{INK}" stroke-width="2" transform="rotate(-8 32 23)"/>
<rect x="8" y="24" width="44" height="28" rx="3" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<path d="M24 24v28M8 36h44" fill="none" stroke="{BLUE}" stroke-width="3"/>
<path d="M24 36c-6-8-12-4-8 0s8 0 8 0c6-8 12-4 8 0s-8 0-8 0z" fill="{PAPER}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>''',
    # 배터리 셀: 원통형 셀 + 번개
    "battery": f'''<rect x="18" y="12" width="28" height="44" rx="5" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<rect x="26" y="6" width="12" height="6" rx="1.5" fill="{INK}"/>
<rect x="18" y="40" width="28" height="16" rx="0" fill="{CREAM}" stroke="{INK}" stroke-width="2"/>
<path d="M35 18l-9 13h7l-4 12 10-15h-7z" fill="{BLUE}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>''',
}
_INDUSTRY_ICON = {"construction": "build", "semiconductor": "package", "franchise_retail": "store",
                  "department_store": "giftcard", "secondary_battery": "battery"}


# ---------------- 2026-11-4: 산업 추가용 일러스트 ----------------
_ICONS.update({
    # 고로·용광로: 노 + 쇳물
    "furnace": f'''<path d="M18 56l4-38h20l4 38z" fill="{SKY}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<path d="M22 18h20M24 10h16v8H24z" fill="{CREAM}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<path d="M26 44c2-4 10-4 12 0v12H26z" fill="#F5A524" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<path d="M46 50h10M50 46v10" {_S}/><path d="M8 56h50" {_S}/>''',
    # 강판 코일
    "coil": f'''<ellipse cx="24" cy="34" rx="14" ry="18" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<ellipse cx="24" cy="34" rx="6" ry="8" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
<path d="M24 16h22c8 0 8 36 0 36H24" fill="{CREAM}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<ellipse cx="24" cy="34" rx="14" ry="18" fill="none" stroke="{INK}" stroke-width="2"/><path d="M30 24c3 4 3 16 0 20" fill="none" stroke="{BLUE}" stroke-width="2"/>''',
    # 자동차
    "car": f'''<path d="M6 40l6-14c2-4 4-6 8-6h22c4 0 6 2 8 6l6 14v8H6z" fill="{SKY}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<path d="M16 28l3-6h24l3 6z" fill="{PAPER}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<circle cx="18" cy="48" r="6" fill="{PAPER}" stroke="{INK}" stroke-width="2"/><circle cx="46" cy="48" r="6" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
<rect x="8" y="36" width="8" height="4" rx="1" fill="{BLUE}"/><rect x="48" y="36" width="8" height="4" rx="1" fill="{CREAM}" stroke="{INK}" stroke-width="1.5"/>''',
    # 플라스크
    "flask": f'''<path d="M26 8h12M28 8v16L14 50c-2 4 0 6 4 6h28c4 0 6-2 4-6L36 24V8" fill="{PAPER}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<path d="M19 42h26l5 9c1 3 0 5-4 5H18c-4 0-5-2-4-5z" fill="{BLUE}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<circle cx="28" cy="48" r="2.5" fill="{SKY}"/><circle cx="36" cy="45" r="2" fill="{SKY}"/><path d="M44 14h8M48 10v8" {_S}/>''',
    # 알약·캡슐
    "pill": f'''<g transform="rotate(-35 26 30)"><rect x="6" y="20" width="40" height="20" rx="10" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<path d="M16 20h10v20H16a10 10 0 0 1 0-20z" fill="{BLUE}" stroke="{INK}" stroke-width="2"/></g>
<circle cx="46" cy="46" r="10" fill="{CREAM}" stroke="{INK}" stroke-width="2"/><path d="M39 46h14" stroke="{INK}" stroke-width="2"/>''',
    # 통신 기지국
    "tower": f'''<path d="M32 22L20 58M32 22l12 36M24 46h16M27 36h10" {_S}/>
<circle cx="32" cy="18" r="5" fill="{BLUE}" stroke="{INK}" stroke-width="2"/>
<path d="M22 10a14 14 0 0 0 0 16M42 10a14 14 0 0 1 0 16M16 6a22 22 0 0 0 0 24M48 6a22 22 0 0 1 0 24" fill="none" stroke="{SKY}" stroke-width="3" stroke-linecap="round"/>
<path d="M12 58h40" {_S}/>''',
    # 은행
    "bank": f'''<path d="M6 24L32 8l26 16z" fill="{CREAM}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<rect x="8" y="24" width="48" height="6" fill="{SKY}" stroke="{INK}" stroke-width="2"/>
<path d="M14 30v20M24 30v20M40 30v20M50 30v20" stroke="{INK}" stroke-width="3"/>
<rect x="6" y="50" width="52" height="6" fill="{SKY}" stroke="{INK}" stroke-width="2"/><circle cx="32" cy="18" r="4" fill="{BLUE}"/>''',
    # 코드·앱 화면
    "code": f'''<rect x="6" y="10" width="52" height="36" rx="4" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>
<path d="M6 18h52" stroke="{INK}" stroke-width="2"/><circle cx="12" cy="14" r="1.6" fill="{INK}"/><circle cx="18" cy="14" r="1.6" fill="{INK}"/>
<path d="M22 26l-6 6 6 6M42 26l6 6-6 6" fill="none" stroke="{BLUE}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M35 24l-6 16" stroke="{INK}" stroke-width="2" stroke-linecap="round"/><path d="M24 54h16M32 46v8" {_S}/>''',
    # 선박
    "ship": f'''<path d="M6 40h52l-8 14H14z" fill="{SKY}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<rect x="14" y="28" width="12" height="12" fill="{CREAM}" stroke="{INK}" stroke-width="2"/>
<rect x="28" y="28" width="12" height="12" fill="{BLUE}" stroke="{INK}" stroke-width="2"/>
<path d="M44 40V20h8v20" fill="{PAPER}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/><path d="M46 26h4" {_S}/>
<path d="M4 60c4-3 8-3 12 0s8 3 12 0 8-3 12 0 8 3 12 0" fill="none" stroke="{BLUE}" stroke-width="2" stroke-linecap="round"/>''',
    # 식품: 그릇 + 김
    "food": f'''<path d="M8 32h48c0 12-10 22-24 22S8 44 8 32z" fill="{CREAM}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<path d="M14 32c2-6 8-8 12-6 2-4 10-4 12 0 4-2 10 0 12 6" fill="{SKY}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
<path d="M22 20c-2-4 2-6 0-10M32 18c-2-4 2-6 0-10M42 20c-2-4 2-6 0-10" fill="none" stroke="{BLUE}" stroke-width="2" stroke-linecap="round"/>
<path d="M24 58h16" {_S}/>''',
})
_INDUSTRY_ICON.update({"steel": "furnace", "automobile": "car", "chemical": "flask", "pharma_bio": "pill",
                       "telecom": "tower", "banking": "bank", "platform": "code", "shipbuilding": "ship",
                       "food_beverage": "food"})


def svg(icon: str, size: int = 64, label: str = "") -> str:
    body = _ICONS.get(icon)
    if body is None:  # 미지정 아이콘: 빈 원
        body = f'<circle cx="32" cy="32" r="22" fill="{CREAM}" stroke="{INK}" stroke-width="2"/>'
    aria = f'role="img" aria-label="{escape(label, quote=True)}"' if label else 'aria-hidden="true"'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{size}" height="{size}" {aria}>'
            f'{body}</svg>')


def img(icon: str, size: int = 64, label: str = "") -> str:
    """st.html은 HTML을 정화(sanitize)하면서 인라인 <svg>를 지운다 → 빈 칸.
    정화를 통과하는 <img src="data:image/svg+xml;base64,…">로 감싸서 넣는다."""
    data = base64.b64encode(svg(icon, size).encode("utf-8")).decode("ascii")
    alt = escape(label, quote=True)
    hidden = "" if label else ' aria-hidden="true"'   # f-string 안에 역슬래시를 넣지 않는다 (Python 3.11 이하에서 문법 오류)
    return (f'<img src="data:image/svg+xml;base64,{data}" width="{size}" height="{size}" alt="{alt}"'
            f'{hidden}>')


def industry_svg(key: str, size: int = 56) -> str:
    return svg(_INDUSTRY_ICON.get(key, ""), size)


def industry_img(key: str, size: int = 56, label: str = "") -> str:
    return img(_INDUSTRY_ICON.get(key, ""), size, label)


def icon_keys() -> set[str]:
    return set(_ICONS)
