"""1단계 — 데이터 수집.

수집 대상은 '공개정보'로 한정한다 (Phase 1~2).
  - OpenDART: 기업개황(업종코드), 최근 사업보고서의 'II. 사업의 내용'
  - 사용자 업로드: 정부·공공기관 산업자료 등 공개자료 (공개 여부를 사용자가 확인해야 함)
  - 데모: 가상의 기업 예시 데이터 (API 키 없이 동작 확인용)
실제 감사 고객의 비공개 자료는 MVP 범위에서 제외한다 (Phase 3 미구현).
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree

import requests

from .clean import strip_markup
from .finance import FinancialData, from_dart_rows
from .models import SourceDoc
from .report_parse import parse_business

DART_BASE = "https://opendart.fss.or.kr/api"
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


class CollectError(RuntimeError):
    pass


# ---------------- OpenDART ----------------
class DartCollector:
    def __init__(self, api_key: str, timeout: int = 30):
        if not api_key:
            raise CollectError("DART_API_KEY가 설정되지 않았습니다.")
        self._key = api_key  # 로그·리포트에 절대 기록하지 않는다
        self.timeout = timeout

    def _get(self, endpoint: str, **params) -> requests.Response:
        r = requests.get(f"{DART_BASE}/{endpoint}", params={"crtfc_key": self._key, **params},
                         timeout=self.timeout)
        r.raise_for_status()
        return r

    def _json(self, endpoint: str, **params) -> dict:
        data = self._get(endpoint, **params).json()
        if data.get("status") not in ("000", None):
            raise CollectError(f"DART {endpoint} 오류 [{data.get('status')}]: {data.get('message')}")
        return data

    def _corps(self) -> list[dict]:
        """전체 고유번호 목록. 하루 단위로 캐시한다."""
        CACHE_DIR.mkdir(exist_ok=True)
        cache = CACHE_DIR / f"corpcode_v2_{date.today():%Y%m%d}.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        z = zipfile.ZipFile(io.BytesIO(self._get("corpCode.xml").content))
        root = ElementTree.fromstring(z.read(z.namelist()[0]))
        corps = [{"corp_code": e.findtext("corp_code"), "corp_name": e.findtext("corp_name"),
                  "stock_code": (e.findtext("stock_code") or "").strip(),
                  "modify_date": (e.findtext("modify_date") or "").strip()}
                 for e in root.iter("list")]
        cache.write_text(json.dumps(corps, ensure_ascii=False), encoding="utf-8")
        return corps

    def search_corps(self, name: str, limit: int = 15) -> list[dict]:
        """회사명 검색 → 후보 목록. 이름이 같은 회사가 여럿이므로 사용자가 고르게 한다.

        순서: 상장사 정확일치 > 상장사 앞부분일치 > 상장사 포함 > 비상장 정확일치 > 비상장 나머지 (짧은 이름 우선)
        """
        return rank_corps(self._corps(), name, limit)

    def find_corp(self, name: str) -> dict:
        """하위호환: 가장 앞선 후보 1개. 화면에서는 search_corps로 후보를 보여주고 고르게 한다."""
        cands = self.search_corps(name, 1)
        if not cands:
            raise CollectError(f"DART에서 '{name}'을(를) 찾을 수 없습니다.")
        return cands[0]

    def company_info(self, corp_code: str) -> dict:
        return self._json("company.json", corp_code=corp_code)

    def latest_annual_report(self, corp_code: str) -> dict:
        try:
            data = self._json("list.json", corp_code=corp_code, pblntf_detail_ty="A001",
                              bgn_de=(date.today() - timedelta(days=550)).strftime("%Y%m%d"),
                              page_count=10)
        except CollectError as e:
            if "[013]" in str(e):  # 조회된 데이터 없음
                raise CollectError("최근 1년 6개월 사이 제출된 사업보고서가 없습니다. "
                                   "비상장·상장폐지·신설 법인일 수 있으니 다른 후보를 고르세요.") from e
            raise
        reports = [r for r in data.get("list", []) if "사업보고서" in r["report_nm"]]
        if not reports:
            raise CollectError("최근 사업보고서를 찾을 수 없습니다.")
        return reports[0]

    def corp_code_for_stock(self, stock_code: str) -> str:
        """종목코드 → 고유번호 (corp_code를 저장하지 않았던 옛 분석 결과용)."""
        hit = next((c for c in self._corps() if stock_code and c["stock_code"] == stock_code), None)
        return hit["corp_code"] if hit else ""

    def recent_disclosures(self, corp_code: str, days: int = 365, limit: int = 100) -> list[dict]:
        """최근 공시 목록 (OpenDART list.json, 모든 공시 유형). 없으면 빈 목록.
        요청 URL에 인증키가 들어 있으므로 네트워크 오류 메시지는 그대로 내보내지 않는다."""
        try:
            data = self._json("list.json", corp_code=corp_code,
                              bgn_de=(date.today() - timedelta(days=days)).strftime("%Y%m%d"),
                              end_de=date.today().strftime("%Y%m%d"), page_count=min(limit, 100),
                              sort="date", sort_mth="desc")
        except CollectError as e:
            if "[013]" in str(e):   # 조회된 데이터 없음
                return []
            raise
        except requests.RequestException as e:
            raise CollectError(f"DART 공시 목록을 불러오지 못했습니다 ({type(e).__name__}).") from None
        return data.get("list", [])

    def document_text(self, rcept_no: str) -> str:
        z = zipfile.ZipFile(io.BytesIO(self._get("document.xml", rcept_no=rcept_no).content))
        text = ""
        for n in z.namelist():
            raw = z.read(n)
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    text += raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
        return text

    @staticmethod
    def business_section(text: str) -> str:
        """'II. 사업의 내용' ~ 'III. 재무에 관한 사항' 구간.

        본문의 참조 문구("'II. 사업의 내용'을 참고")나 목차 표에도 같은 글자가 나오므로,
        DART 문서 구조의 장 제목(<TITLE>)을 기준으로 자른다. 구조가 없을 때만 글자 검색으로 대체.
        """
        m = re.search(r"<TITLE[^>]*>\s*II\.\s*사업의\s*내용\s*</TITLE>(.*?)<TITLE[^>]*>\s*III\.\s*재무에\s*관한\s*사항",
                      text, re.S | re.I)
        if not m:
            m = re.search(r"II\.\s*사업의\s*내용(.*?)III\.\s*재무에\s*관한\s*사항", text, re.S)
        if not m:
            raise CollectError("사업보고서에서 '사업의 내용' 구간을 찾지 못했습니다.")
        return m.group(1)

    RPT_LIMIT = 40000  # 대기업 주석은 길다. 자르면 '주석에 없음' 오탐이 생기므로 잘렸는지 반드시 기록한다.

    @staticmethod
    def rpt_sections(text: str, limit: int = RPT_LIMIT) -> tuple[str | None, str | None, dict[str, bool]]:
        """특수관계자 거래가 나오는 두 구간 + 잘림 여부. 보고서마다 형식이 달라 못 찾으면 None → '확인 필요'.

        1) 본문 'X. 대주주 등과의 거래내용' ~ 다음 장
        2) 재무제표 주석 중 '특수관계자' 제목의 주석 ~ 다음 번호 주석
        """
        plain = strip_markup(text)  # 문단·표 행 경계를 줄바꿈으로 바꾼 뒤 찾는다
        biz = re.search(r"(?:X|Ⅹ|10)\.\s*대주주\s*등과의\s*거래\s*내용(.*?)\n\s*(?:XI|Ⅺ|11)\.\s", plain, re.S)
        notes = re.search(r"\n\s*\d{1,2}\.\s*특수관계자[^\n]{0,30}\n(.*?)(?=\n\s*\d{1,2}\.\s*[가-힣])", plain, re.S)
        b, n = (biz.group(1) if biz else None), (notes.group(1) if notes else None)
        cut = {"business": bool(b and len(b) > limit), "notes": bool(n and len(n) > limit)}
        return (b[:limit] if b else None, n[:limit] if n else None, cut)

    def financials(self, corp_code: str, rpt: dict) -> FinancialData | None:
        """단일회사 전체 재무제표(사업보고서). 연결 우선, 없으면 별도. 실패해도 분석은 계속한다."""
        m = re.search(r"\((\d{4})\.\d{2}\)", rpt["report_nm"])
        if not m:
            return None
        year = int(m.group(1))
        for fs_div, basis in (("CFS", "연결"), ("OFS", "별도")):
            data = self._get("fnlttSinglAcntAll.json", corp_code=corp_code, bsns_year=year,
                             reprt_code="11011", fs_div=fs_div).json()
            if data.get("status") == "000" and data.get("list"):
                return from_dart_rows(
                    data["list"], year, title=f"{rpt['report_nm'].strip()} {basis}재무제표", basis=basis,
                    url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rpt['rcept_no']}")
        return None

    def collect(self, name: str = "", corp_code: str = "") -> tuple[list[SourceDoc], dict]:
        """corp_code를 주면 그 회사를 그대로 쓴다 (화면에서 후보를 고른 경우). 이름만 주면 첫 후보."""
        corp = {"corp_code": corp_code} if corp_code else self.find_corp(name)
        info = self.company_info(corp["corp_code"])
        if not is_listed(info):
            raise CollectError(f"'{info.get('corp_name')}'은(는) 현재 상장사가 아닙니다(법인구분: {info.get('corp_cls') or '-'}). "
                               "분석 대상은 유가증권·코스닥·코넥스 상장사만입니다.")
        rpt = self.latest_annual_report(corp["corp_code"])
        full = self.document_text(rpt["rcept_no"])
        url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rpt['rcept_no']}"
        overview = (f"회사명: {info.get('corp_name')}\n업종코드(KSIC): {info.get('induty_code')}\n"
                    f"설립일: {info.get('est_dt')}\n홈페이지: {info.get('hm_url')}")
        docs = [
            SourceDoc(doc_id="S01", title=f"{info.get('corp_name')} 기업개황", publisher="DART",
                      url="https://opendart.fss.or.kr", scope="company", raw_text=overview),
            SourceDoc(doc_id="S02", title=f"{rpt['report_nm'].strip()} II. 사업의 내용",
                      publisher="DART", published=rpt["rcept_dt"],
                      url=url, scope="company", raw_text=self.business_section(full)),  # 정제 단계에서 마크업 제거
        ]
        rpt_docs = {}
        biz, notes, rpt_truncated = self.rpt_sections(full)
        for key, sid, text, title in (("business", "S03", biz, "X. 대주주 등과의 거래내용"),
                                      ("notes", "S04", notes, "재무제표 주석 — 특수관계자")):
            if text:
                docs.append(SourceDoc(doc_id=sid, title=f"{rpt['report_nm'].strip()} {title}", publisher="DART",
                                      published=rpt["rcept_dt"], url=url, scope="company", raw_text=text))
                rpt_docs[key] = sid
        m = re.search(r"\((\d{4})\.\d{2}\)", rpt["report_nm"])
        biz_raw = self.business_section(full)
        profile = {k: (info.get(k) or "").strip() for k in
                   ("corp_code", "corp_name", "corp_name_eng", "stock_name", "stock_code", "ceo_nm", "corp_cls", "jurir_no",
                    "adres", "hm_url", "induty_code", "est_dt", "acc_mt")}
        profile.update(report_nm=rpt["report_nm"].strip(), rcept_dt=rpt["rcept_dt"], url=url)
        meta = {"corp_name": info.get("corp_name"), "induty_code": info.get("induty_code", ""),
                "company_profile": profile, "business_sections": parse_business(biz_raw),
                "stock_code": (info.get("stock_code") or "").strip(),
                "financials": self.financials(corp["corp_code"], rpt), "rpt_docs": rpt_docs, "rpt_truncated": rpt_truncated,
                "report_year": int(m.group(1)) if m else None}
        return docs, meta


def _norm(s: str) -> str:
    return re.sub(r"\s+|\(주\)|㈜|주식회사", "", s or "").lower()


# 흔히 쓰는 약칭·옛 이름 → DART 등록명 (등록명과 글자가 달라 검색에 안 걸리는 경우만)
ALIASES = {"포스코": "POSCO홀딩스", "posco": "POSCO홀딩스", "현대차": "현대자동차", "하이닉스": "SK하이닉스",
           "삼전": "삼성전자", "엘지전자": "LG전자", "엘지화학": "LG화학", "네이버": "NAVER", "케이티": "KT",
           "엘지": "LG", "에스케이": "SK"}


def rank_corps(corps: list[dict], name: str, limit: int = 15, listed_only: bool = True) -> list[dict]:
    """회사명 후보 순위 (순수 함수 — 테스트 가능).

    listed_only: 종목코드가 없는 비상장 회사는 후보에서 뺀다 (분석 대상은 상장사만).
    """
    q = _norm(name)
    if not q:
        return []
    if listed_only:
        corps = [c for c in corps if c.get("stock_code")]
    alias = _norm(ALIASES.get(q, ""))

    def tier(c: dict) -> int | None:
        # 상장폐지 회사도 고유번호 파일에 종목코드가 남아 있다 → 정보가 오래 갱신되지 않았으면 비상장처럼 취급
        n, listed = _norm(c["corp_name"]), bool(c.get("stock_code")) and not is_stale(c)
        if alias and n == alias:
            return -1
        if n == q:
            return 0 if listed else 3
        if n.startswith(q):
            return 1 if listed else 4
        if q in n:
            return 2 if listed else 5
        return None

    scored = [(t, len(c["corp_name"]), -int(c.get("modify_date") or 0), c) for c in corps if (t := tier(c)) is not None]
    scored.sort(key=lambda x: x[:3])   # 단계 → 짧은 이름 → 최근 갱신 순
    return [x[3] for x in scored[:limit]]


LISTED_CLS = {"Y": "유가증권시장", "K": "코스닥", "N": "코넥스"}  # DART 기업개황 corp_cls (E = 기타·비상장)


def is_listed(info: dict) -> bool:
    """기업개황 기준 현재 상장 여부. 상장폐지 회사는 종목코드가 남아 있어도 corp_cls가 E."""
    return info.get("corp_cls") in LISTED_CLS


STALE_YEARS = 3


def is_stale(c: dict) -> bool:
    """DART 고유번호 정보가 STALE_YEARS년 넘게 갱신되지 않음 → 상장폐지·휴면 가능성."""
    d = c.get("modify_date") or ""
    return len(d) == 8 and d.isdigit() and int(d[:4]) < date.today().year - STALE_YEARS


def corp_label(c: dict) -> str:
    if not c.get("stock_code"):
        return f"{c['corp_name']} · 비상장"
    if is_stale(c):
        return f"{c['corp_name']} · 종목코드 {c['stock_code']} (정보 갱신 {c['modify_date'][:4]}년 — 상장폐지 가능)"
    return f"{c['corp_name']} · 상장 {c['stock_code']}"


# ---------------- 사용자 업로드 (공개 산업자료) ----------------
def uploaded_doc(doc_id: str, title: str, publisher: str, published: str, url: str,
                 text: str) -> SourceDoc:
    return SourceDoc(doc_id=doc_id, title=title, publisher=publisher, published=published,
                     url=url, scope="industry", raw_text=text)


# ---------------- 데모 ----------------
def list_demos() -> dict[str, Path]:
    return {json.loads(p.read_text(encoding="utf-8"))["company"]: p
            for p in sorted(SAMPLE_DIR.glob("*.json"))}


def load_demo(path: Path) -> tuple[list[SourceDoc], dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    docs = [SourceDoc(**d) for d in data["sources"]]
    fin = data.get("financials")
    if fin:  # JSON은 연도 키가 문자열이므로 정수로 변환
        fin = FinancialData(**{**fin, "amounts": {k: {int(y): v for y, v in d.items()}
                                                  for k, d in fin["amounts"].items()}})
    return docs, {"corp_name": data["company"], "induty_code": data.get("induty_code", ""), "financials": fin,
                  "rpt_docs": data.get("rpt_docs", {}), "rpt_recorded": data.get("rpt_recorded", {}),
                  "report_year": data.get("report_year")}
