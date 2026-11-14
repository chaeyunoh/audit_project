"""AI Audit Industry Scanner — 진입점.

목적: 감사인이 처음 맡은 회사의 산업 특성을 공시로 확인하고, 위험신호와 확인 질문으로 이어 간다.
  기업 분석이 중심 화면이고, 산업 깊이 보기·목록은 참고용이다.

실행: streamlit run app.py
"""
from __future__ import annotations

import os
import sys

if __name__ == "__main__":
    # 'python app.py'(VS Code ▶ 실행 등)로 켜면 Streamlit 런타임이 없어 페이지가 동작하지 않는다
    # → 같은 인터프리터로 'streamlit run app.py'를 대신 실행한다. streamlit run 안에서는 그대로 통과.
    from streamlit.runtime import exists as _runtime_exists
    if not _runtime_exists():
        import subprocess
        sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", __file__, *sys.argv[1:]]))

import streamlit as st
from dotenv import load_dotenv

import ui

# DART_API_KEY를 읽는 곳 (먼저 찾은 값을 쓴다)
#  1) 이미 설정된 환경변수   2) 로컬의 .env 파일   3) 웹 배포(Streamlit Community Cloud)의 Secrets 설정
load_dotenv(override=False)
if not os.getenv("DART_API_KEY"):
    try:
        if "DART_API_KEY" in st.secrets:
            os.environ["DART_API_KEY"] = str(st.secrets["DART_API_KEY"])
    except Exception:  # 로컬에는 secrets.toml이 없어 st.secrets 접근 자체가 실패할 수 있다 — 무시
        pass

st.set_page_config(page_title="AI Audit Industry Scanner", page_icon="🔎", layout="wide")
ui.inject_css()

page = st.navigation(
    {
        "기업 분석": [
            st.Page("app_pages/company.py", title="기업 분석", icon=":material/domain:", default=True,
                    help="회사 공시로 산업 특성을 확인하고 Risk Map·확인 질문·재무 신호·중요성·특수관계자 교차점검을 봅니다."),
        ],
        "참고 · 산업 이해": [
            st.Page("app_pages/industry.py", title="산업 깊이 보기", icon=":material/account_tree:",
                    help="한 산업의 사업 구조, 가치사슬별 특성, 계정·주장 지도, 재무 지표. 기업 분석 결과에서 바로 넘어올 수 있습니다."),
            st.Page("app_pages/overview.py", title="산업 목록", icon=":material/apps:",
                    help="지식베이스에 있는 산업을 카드로 훑어봅니다."),
        ],
        # 보류: 본부별 산업(app_pages/divisions.py), 산업 비교(app_pages/compare.py) — 본부 구분은 작성자 추정이 섞여 있어 숨김
    },
    position="top",
)

st.title(page.title, icon=page.icon, anchor=False)
page.run()
