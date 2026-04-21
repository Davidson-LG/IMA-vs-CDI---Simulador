"""
IMA-B 5 vs CDI — Simulador de Retornos
Aplicação principal Streamlit
"""
import sys
import os

# Garante que o diretório raiz do app está no sys.path (necessário no Streamlit Cloud)
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st

st.set_page_config(
    page_title="IMA-B 5 vs CDI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.session_state import init_session_state
init_session_state()

# ─── Estilo global ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Paleta de cores */
:root {
    --azul-escuro: #0D1B2A;
    --azul-medio: #1B4F72;
    --azul-claro: #2E86C1;
    --verde: #1E8449;
    --vermelho: #C0392B;
    --amarelo: #D4AC0D;
    --cinza-bg: #F4F6F7;
    --branco: #FFFFFF;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0D1B2A 0%, #1B4F72 100%);
}
[data-testid="stSidebar"] * {
    color: white !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stDateInput label {
    color: #BDC3C7 !important;
    font-size: 0.85rem;
}

/* Cards de métricas */
.metric-card {
    background: white;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    border-left: 5px solid #2E86C1;
    margin-bottom: 12px;
}
.metric-card.verde { border-left-color: #1E8449; }
.metric-card.vermelho { border-left-color: #C0392B; }
.metric-card.amarelo { border-left-color: #D4AC0D; }

/* Títulos de seção */
.section-title {
    font-size: 1.4rem;
    font-weight: 700;
    color: #0D1B2A;
    border-bottom: 3px solid #2E86C1;
    padding-bottom: 8px;
    margin: 24px 0 16px 0;
}

/* Badge de cenário */
.badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-right: 8px;
}
.badge-focus { background: #D6EAF8; color: #1A5276; }
.badge-otimista { background: #D5F5E3; color: #1E8449; }
.badge-alternativo { background: #FDEDEC; color: #C0392B; }

/* Tabelas */
.stDataFrame { border-radius: 8px; overflow: hidden; }

/* Botões primários */
.stButton > button {
    background: #2E86C1;
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 8px 20px;
    transition: background 0.2s;
}
.stButton > button:hover { background: #1B4F72; }

/* Info boxes */
.info-box {
    background: #EBF5FB;
    border-left: 4px solid #2E86C1;
    border-radius: 4px;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 0.9rem;
}
.warning-box {
    background: #FEF9E7;
    border-left: 4px solid #D4AC0D;
    border-radius: 4px;
    padding: 12px 16px;
    margin: 8px 0;
}
</style>
""", unsafe_allow_html=True)

# ─── Navegação ─────────────────────────────────────────────────────────────────
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

    # Indicador do cenário ativo
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
    <div style='font-size:0.8rem; color:#BDC3C7; margin-bottom:4px'>Cenário ativo:</div>
    <span class='badge {cls_ipca}'>IPCA: {label_ipca}</span><br><br>
    <span class='badge {cls_selic}'>Selic: {label_selic}</span>
    """, unsafe_allow_html=True)

    focus_pub = st.session_state.get("focus_data_publicacao", "N/D")
    st.markdown(f"""
    <div style='font-size:0.75rem; color:#95A5A6; margin-top:12px'>
    📡 Focus: {focus_pub}
    </div>
    """, unsafe_allow_html=True)

# ─── Roteamento ────────────────────────────────────────────────────────────────
if "Cenários Principais" in pagina:
    from pages.cenarios import render
    render()
elif "Mês a Mês" in pagina:
    from pages.mes_a_mes import render
    render()
elif "Histórico VNA" in pagina:
    from pages.historico_vna import render
    render()
elif "Parâmetros" in pagina:
    from pages.parametros import render
    render()
elif "Carteira" in pagina:
    from pages.carteira import render
    render()
