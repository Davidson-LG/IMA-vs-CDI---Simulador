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
from utils.persistence import load_config, save_config, load_vna
load_config()   # restaura configurações salvas no browser
init_session_state()

# ── Carrega Focus automaticamente (só se ainda não carregado nesta sessão) ──
if not st.session_state.get("_focus_loaded"):
    try:
        from utils.focus_api import get_focus_ipca_mensal, get_focus_selic_copom
        from utils.session_state import selic_list_to_reunioes
        from datetime import date as _date

        # IPCA Base
        if not st.session_state.get("ipca_base"):
            df_ipca = get_focus_ipca_mensal()
            if not df_ipca.empty:
                st.session_state["ipca_base"] = df_ipca.to_dict("records")

        # Selic Base
        if not st.session_state.get("selic_base"):
            df_selic = get_focus_selic_copom()
            if not df_selic.empty:
                rows = []
                for _, row in df_selic.iterrows():
                    dt = row["data_reuniao"]
                    if hasattr(dt, "date"): dt = dt.date()
                    rows.append({
                        "reuniao_label": str(row["Reuniao"]),
                        "data_reuniao":  dt,
                        "taxa_aa":       float(row["taxa_aa"]),
                    })
                st.session_state["selic_base"] = sorted(rows, key=lambda x: x["data_reuniao"])
    except Exception:
        pass
    st.session_state["_focus_loaded"] = True

# ── Restaura VNA do browser (só se ainda não carregado) ──
if st.session_state.get("vna_historico") is None or    st.session_state["vna_historico"].empty:
    _vna_restored = load_vna()
    if _vna_restored is not None and not _vna_restored.empty:
        st.session_state["vna_historico"] = _vna_restored

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

/* ── Esconde navegação automática de páginas do Streamlit ── */
[data-testid="stSidebarNavItems"] { display: none !important; }
[data-testid="stSidebarNavSeparator"] { display: none !important; }
[data-testid="stSidebarNav"] { display: none !important; }
section[data-testid="stSidebar"] > div > div:first-child ul { display: none !important; }
nav[data-testid="stSidebarNav"] { display: none !important; }
div[data-testid="stSidebarNavItems"] { display: none !important; }
.st-emotion-cache-1eo1tir { display: none !important; }
.st-emotion-cache-16idsys { display: none !important; }
/* Esconde o bloco de páginas acima do radio (múltiplos seletores para robustez) */
section[data-testid="stSidebar"] ul[data-testid="stSidebarNavItems"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 📊 IMA-B 5 vs CDI")
    st.markdown("---")
    pagina = st.radio(
        "Navegação",
        options=[
            "📉 Cenários Principais",
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
    # Busca data do Focus diretamente (com cache de 24h)
    from utils.focus_api import get_focus_data_publicacao
    focus_pub = get_focus_data_publicacao()
    st.markdown(f"<div style='font-size:0.75rem;color:#95A5A6;margin-top:12px'>📡 Focus: {focus_pub}</div>",
                unsafe_allow_html=True)

if "Cenários Principais" in pagina:
    from pages._cenarios import render; render()
elif "Mês a Mês" in pagina:
    from pages._mes_a_mes import render; render()
elif "Histórico VNA" in pagina:
    from pages._historico_vna import render; render()
elif "Parâmetros" in pagina:
    from pages._parametros import render; render()
elif "Carteira" in pagina:
    from pages._carteira import render; render()
