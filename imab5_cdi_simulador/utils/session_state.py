"""
Gerenciamento de estado compartilhado entre páginas do Streamlit.
"""
import streamlit as st
from datetime import date
import pandas as pd


def init_session_state():
    """Inicializa variáveis de estado padrão."""

    defaults = {
        # Parâmetros IMA-B 5
        "taxa_real_aa": 7.75,
        "duration_du": 496,

        # Datas
        "data_inicio": date.today(),
        "data_fim": date(date.today().year + 1, date.today().month, date.today().day),

        # Cenário ativo (base/otimista/alternativo)
        "cenario_ativo_ipca": "base",
        "cenario_ativo_selic": "base",

        # IPCA - três cenários (lista de dicts {mes, valor})
        "ipca_base": [],       # preenchido pelo Focus
        "ipca_otimista": [],   # manual
        "ipca_alternativo": [],  # manual

        # Selic - três cenários (lista de dicts {reuniao, taxa})
        "selic_base": [],      # preenchido pelo Focus
        "selic_otimista": [],
        "selic_alternativo": [],

        # VNA carregado
        "vna_uploaded_file": None,
        "vna_historico": pd.DataFrame(columns=["Data", "VNA", "Ref"]),

        # Abertura/fechamento cenários principais
        "cenario1_variacao": -0.50,   # fechamento (negativo = redução da taxa)
        "cenario2_variacao": 0.0,     # estabilidade
        "cenario3_variacao": 0.50,    # abertura

        # Carteira
        "peso_cdi": 50.0,
        "peso_imab5": 50.0,
        "carteira_variacao": 0.0,

        # Focus publicação
        "focus_data_publicacao": "N/D",
    }

    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def get_ipca_cenario(cenario: str) -> list:
    """Retorna lista de IPCA para o cenário selecionado."""
    mapping = {
        "base": st.session_state.get("ipca_base", []),
        "otimista": st.session_state.get("ipca_otimista", []),
        "alternativo": st.session_state.get("ipca_alternativo", []),
    }
    data = mapping.get(cenario, [])
    # fallback para base se cenário manual vazio
    if not data:
        data = st.session_state.get("ipca_base", [])
    return data


def get_selic_cenario(cenario: str) -> list:
    """Retorna lista de Selic para o cenário selecionado."""
    mapping = {
        "base": st.session_state.get("selic_base", []),
        "otimista": st.session_state.get("selic_otimista", []),
        "alternativo": st.session_state.get("selic_alternativo", []),
    }
    data = mapping.get(cenario, [])
    if not data:
        data = st.session_state.get("selic_base", [])
    return data


def ipca_list_to_df(ipca_list: list) -> pd.DataFrame:
    """Converte lista de IPCA para DataFrame {DataReferencia, Mediana}."""
    if not ipca_list:
        return pd.DataFrame(columns=["DataReferencia", "Mediana"])
    return pd.DataFrame(ipca_list)


def selic_list_to_reunioes(selic_list: list) -> list:
    """Converte lista de Selic para formato usado no cálculo CDI."""
    result = []
    for item in selic_list:
        if "data_reuniao" in item and "taxa_aa" in item:
            result.append(item)
    return result
