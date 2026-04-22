"""
IMA-B 5 vs CDI — Simulador de Retornos
"""
import sys
import os

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import streamlit as st

st.set_page_config(
    page_title="IMA-B 5 vs CDI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.session_state import init_session_state
init_session_state()

st.markdown("""
<style>
.section-title {
    font-size: 1.4rem; font-weight: 700; color: #0D1B2A;
    border-bottom: 3px solid #2E86C1;
    padding-bottom: 8px; margin: 24px 0 16px 0;
}
.badge {
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    font-size: 0.78rem; font-weight: 600; margin-right: 8px;
}
.badge-focus { background: #D6EAF8; color: #1A5276; }
.badge-otimista { background: #D5F5E3; color: #1E8449; }
.badge-alternativo { background: #FDEDEC; color: #C0392B; }
.info-box {
    background: #EBF5FB; border-left: 4px solid #2E86C1;
    border-radius: 4px; padding: 12px 16px; margin: 8px 0; font-size: 0.9rem;
}
.warning-box {
    background: #FEF9E7; border-left: 4px solid #D4AC0D;
    border-radius: 4px; padding: 12px 16px; margin: 8px 0;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0D1B2A 0%, #1B4F72 100%);
}
[data-testid="stSidebar"] * { color: white !important; }
.stButton > button {
    background: #2E86C1; color: white; border: none;
    border-radius: 8px; font-weight: 600; padding: 8px 20px;
}
.stButton > button:hover { background: #1B4F72; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 📊 IMA-B 5 vs CDI")
    st.markdown("---")
    pagina = st.radio(
        "Navegação",
        options=[
            "🏠 Cenários Principais",
            "📅 Retorno Mês a Mês",
            "📈 Histórico VNA",
            "⚙️ Parâmetros",
            "💼 Simulador de Carteira",
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")
    cenario_ipca = st.session_state.get("cenario_ativo_ipca", "base")
    cenario_selic = st.session_state.get("cenario_ativo_selic", "base")
    badges = {
        "base": ("📌 Focus/Base", "badge-focus"),
        "otimista": ("✅ Otimista", "badge-otimista"),
        "alternativo": ("⚠️ Alternativo", "badge-alternativo"),
    }
    label_ipca, cls_ipca = badges.get(cenario_ipca, badges["base"])
    label_selic, cls_selic = badges.get(cenario_selic, badges["base"])
    st.markdown(f"""
    <div style='font-size:0.8rem;color:#BDC3C7;margin-bottom:4px'>Cenário ativo:</div>
    <span class='badge {cls_ipca}'>IPCA: {label_ipca}</span><br><br>
    <span class='badge {cls_selic}'>Selic: {label_selic}</span>
    """, unsafe_allow_html=True)
    focus_pub = st.session_state.get("focus_data_publicacao", "N/D")
    st.markdown(f"<div style='font-size:0.75rem;color:#95A5A6;margin-top:12px'>📡 Focus: {focus_pub}</div>",
                unsafe_allow_html=True)

if "Cenários Principais" in pagina:
    from pages.cenarios import render; render()
elif "Mês a Mês" in pagina:
    from pages.mes_a_mes import render; render()
elif "Histórico VNA" in pagina:
    from pages.historico_vna import render; render()
elif "Parâmetros" in pagina:
    from pages.parametros import render; render()
elif "Carteira" in pagina:
    from pages.carteira import render; render()
