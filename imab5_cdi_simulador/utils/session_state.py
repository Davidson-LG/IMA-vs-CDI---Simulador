"""
Session state: inicialização e helpers para Streamlit.
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


# ── Inicialização ──────────────────────────────────────────────────────────────

def init_session_state():
    hoje = date.today()

    defaults = {
        "data_inicio":       hoje,
        "data_fim":          date(hoje.year, 12, 31),
        "taxa_real_aa":      7.75,
        "duration_du":       496,
        "cenario_ativo_selic": "base",
        "cenario_ativo_ipca":  "base",
        "vna_historico":     pd.DataFrame(columns=["Data","VNA","Ref","Índice"]),
        # Selic cenários
        "selic_base":        [],
        "selic_otimista":    [],
        "selic_alternativo": [],
        # IPCA cenários — valores MENSAIS por ciclo 15-a-15
        # Formato: [{mes: "MM/YYYY", ipca: float%}, ...]
        "ipca_base":         [],
        "ipca_otimista":     [],
        "ipca_alternativo":  [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Selic helpers ──────────────────────────────────────────────────────────────

def get_selic_cenario(cenario: str) -> list:
    """Retorna lista de dicts {reuniao, data_reuniao, taxa_aa}."""
    return st.session_state.get(f"selic_{cenario}", [])


def selic_list_to_reunioes(selic_list: list) -> list:
    """Converte lista de selic para formato aceito por calcular_retorno_cdi."""
    result = []
    for item in selic_list:
        try:
            dt = item.get("data_reuniao")
            if isinstance(dt, str):
                dt = pd.to_datetime(dt).date()
            elif hasattr(dt, "date"):
                dt = dt.date()
            result.append({
                "data_reuniao": dt,
                "taxa_aa":      float(item.get("taxa_aa", 14.75)),
            })
        except Exception:
            pass
    return sorted(result, key=lambda x: x["data_reuniao"])


# ── IPCA helpers ───────────────────────────────────────────────────────────────

def get_ipca_cenario(cenario: str) -> list:
    """Retorna lista de dicts {mes: 'MM/YYYY', ipca: float%}."""
    return st.session_state.get(f"ipca_{cenario}", [])


def ipca_list_to_df(ipca_list: list) -> pd.DataFrame:
    """
    Converte lista IPCA para DataFrame {DataReferencia: Timestamp, Mediana: float}.
    Aceita dois formatos:
      - Base (Focus):  {"DataReferencia": Timestamp, "Mediana": float}
      - Manual:        {"mes": "MM/YYYY", "ipca": float}
    """
    rows = []
    for item in ipca_list:
        try:
            # Formato Focus: tem DataReferencia
            if "DataReferencia" in item and item["DataReferencia"] is not None:
                dt = pd.to_datetime(item["DataReferencia"])
                val = float(item.get("Mediana", item.get("ipca", 0.0)))
            # Formato manual: tem mes
            elif "mes" in item:
                mes_str = str(item["mes"]).strip()
                if "/" in mes_str:
                    parts = mes_str.split("/")
                    m, y = int(parts[0]), int(parts[1])
                    dt = pd.Timestamp(date(y, m, 1))
                else:
                    dt = pd.to_datetime(mes_str)
                val = float(item.get("ipca", item.get("Mediana", 0.0)))
            else:
                continue

            if pd.isna(dt):
                continue
            rows.append({"DataReferencia": dt, "Mediana": val})
        except Exception:
            pass
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["DataReferencia", "Mediana"]
    )
