"""
Integração com a API do Relatório Focus (Banco Central do Brasil).
"""
import requests
import pandas as pd
import streamlit as st
from datetime import date, datetime
import re

FOCUS_BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"

# Datas de reunião COPOM conhecidas (fallback quando API indisponível)
# Fonte: BCB - calendário de reuniões
COPOM_DATES_FALLBACK = {
    "1/2026": date(2026, 1, 28), "2/2026": date(2026, 3, 18),
    "3/2026": date(2026, 5, 7),  "4/2026": date(2026, 6, 17),
    "5/2026": date(2026, 7, 29), "6/2026": date(2026, 9, 16),
    "7/2026": date(2026, 11, 4), "8/2026": date(2026, 12, 9),
    "1/2027": date(2027, 1, 27), "2/2027": date(2027, 3, 17),
    "3/2027": date(2027, 5, 5),  "4/2027": date(2027, 6, 16),
    "5/2027": date(2027, 7, 28), "6/2027": date(2027, 9, 15),
    "7/2027": date(2027, 11, 3), "8/2027": date(2027, 12, 8),
    "1/2028": date(2028, 1, 26), "2/2028": date(2028, 3, 15),
    "3/2028": date(2028, 5, 3),  "4/2028": date(2028, 6, 14),
}


def _get_latest_focus_date(indicador: str = "IPCA", suavizado: str = "N") -> str | None:
    """Retorna a data da publicação mais recente do Focus para o indicador."""
    try:
        url = (
            f"{FOCUS_BASE}/ExpectativaMercadoMensais"
            f"?$filter=Indicador eq '{indicador}' and Suavizado eq '{suavizado}'"
            f"&$top=1&$format=json&$select=Data&$orderby=Data desc"
        )
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            vals = r.json().get("value", [])
            if vals:
                return vals[0]["Data"]
    except Exception:
        pass
    return None


@st.cache_data(ttl=3600 * 6)
def get_focus_ipca_mensal() -> pd.DataFrame:
    """
    Busca projeções mensais de IPCA do Focus (mediana), último dado disponível.
    Retorna DataFrame com colunas: DataReferencia (Timestamp), Mediana (float %)
    """
    try:
        ultima = _get_latest_focus_date("IPCA", "N")
        if not ultima:
            return _focus_ipca_fallback()

        url = (
            f"{FOCUS_BASE}/ExpectativaMercadoMensais"
            f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N' and Data eq '{ultima}'"
            f"&$top=36&$format=json&$select=DataReferencia,Mediana"
            f"&$orderby=DataReferencia asc"
        )
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return _focus_ipca_fallback()

        vals = r.json().get("value", [])
        if not vals:
            return _focus_ipca_fallback()

        rows = []
        hoje = date.today().replace(day=1)
        for v in vals:
            try:
                # DataReferencia vem como "04/2026"
                mes_str = v["DataReferencia"]  # "MM/YYYY"
                dt = datetime.strptime(mes_str, "%m/%Y").date()
                if dt >= hoje and v["Mediana"] is not None:
                    rows.append({
                        "DataReferencia": pd.Timestamp(dt),
                        "Mediana": float(v["Mediana"]),
                        "MesLabel": mes_str,
                    })
            except Exception:
                continue

        if not rows:
            return _focus_ipca_fallback()

        df = pd.DataFrame(rows).sort_values("DataReferencia").reset_index(drop=True)
        return df

    except Exception:
        return _focus_ipca_fallback()


def _focus_ipca_fallback() -> pd.DataFrame:
    """Valores padrão caso API indisponível — baseados no último Focus conhecido."""
    from dateutil.relativedelta import relativedelta
    # Valores aproximados do Focus de abril/2026
    defaults = [0.66, 0.37, 0.33, 0.20, 0.28, 0.34, 0.15, 0.22, 0.38,
                0.36, 0.26, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30,
                0.30, 0.30, 0.30, 0.30, 0.30, 0.30]
    rows = []
    ref = date.today().replace(day=1)
    for v in defaults:
        rows.append({
            "DataReferencia": pd.Timestamp(ref),
            "Mediana": v,
            "MesLabel": ref.strftime("%m/%Y"),
        })
        ref = (ref + relativedelta(months=1))
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600 * 6)
def get_focus_selic_copom() -> pd.DataFrame:
    """
    Busca projeções de Selic por reunião do COPOM (último dado Focus disponível).
    Retorna DataFrame com colunas:
      - Reuniao: str "1/2026"
      - data_reuniao: date
      - taxa_aa: float (% a.a.)
    Ordenado por data de reunião.
    """
    try:
        # Busca última data disponível para Selic
        url_last = (
            f"{FOCUS_BASE}/ExpectativasMercadoSelic"
            f"?$top=1&$format=json&$select=Data&$orderby=Data desc"
        )
        r = requests.get(url_last, timeout=15)
        if r.status_code != 200:
            return _focus_selic_fallback()

        vals = r.json().get("value", [])
        if not vals:
            return _focus_selic_fallback()
        ultima = vals[0]["Data"]

        # Busca todas as reuniões da última publicação
        url = (
            f"{FOCUS_BASE}/ExpectativasMercadoSelic"
            f"?$filter=Data eq '{ultima}'"
            f"&$top=50&$format=json&$select=Reuniao,Mediana"
            f"&$orderby=Reuniao asc"
        )
        r2 = requests.get(url, timeout=15)
        if r2.status_code != 200:
            return _focus_selic_fallback()

        vals2 = r2.json().get("value", [])
        if not vals2:
            return _focus_selic_fallback()

        rows = []
        seen = set()
        for v in vals2:
            reuniao = v.get("Reuniao", "")
            if not reuniao or reuniao in seen:
                continue
            seen.add(reuniao)
            mediana = v.get("Mediana")
            if mediana is None:
                continue
            dt = _parse_reuniao_to_date(reuniao)
            if dt is None:
                continue
            rows.append({
                "Reuniao": reuniao,
                "data_reuniao": dt,
                "taxa_aa": float(mediana),
            })

        if not rows:
            return _focus_selic_fallback()

        df = pd.DataFrame(rows)
        df = df.sort_values("data_reuniao").reset_index(drop=True)
        # Filtra apenas reuniões futuras (a partir de hoje)
        df = df[df["data_reuniao"] >= date.today()].reset_index(drop=True)
        return df

    except Exception:
        return _focus_selic_fallback()


def _parse_reuniao_to_date(reuniao: str) -> date | None:
    """
    Converte string de reunião COPOM para date.
    Formato: "N/AAAA" onde N é o número da reunião no ano.
    Usa calendário oficial BCB quando disponível, senão estima.
    """
    # Primeiro tenta o mapa de datas conhecidas
    if reuniao in COPOM_DATES_FALLBACK:
        return COPOM_DATES_FALLBACK[reuniao]

    try:
        parts = reuniao.split("/")
        num = int(parts[0])   # número da reunião no ano (1-8)
        ano = int(parts[1])   # ano
        # Estimativa: 8 reuniões/ano, ~45 dias de intervalo, início em janeiro
        # Reunião 1 ≈ final de janeiro, reunião 8 ≈ início de dezembro
        meses_estimados = {1: 1, 2: 3, 3: 5, 4: 6, 5: 7, 6: 9, 7: 11, 8: 12}
        mes = meses_estimados.get(num, num * 2 - 1)
        return date(ano, min(mes, 12), 15)
    except Exception:
        return None


def _focus_selic_fallback() -> pd.DataFrame:
    """Valores padrão para Selic baseados no Focus de abril/2026."""
    rows = [
        {"Reuniao": "3/2026", "data_reuniao": date(2026, 5, 7),  "taxa_aa": 15.00},
        {"Reuniao": "4/2026", "data_reuniao": date(2026, 6, 17), "taxa_aa": 15.25},
        {"Reuniao": "5/2026", "data_reuniao": date(2026, 7, 29), "taxa_aa": 15.25},
        {"Reuniao": "6/2026", "data_reuniao": date(2026, 9, 16), "taxa_aa": 15.00},
        {"Reuniao": "7/2026", "data_reuniao": date(2026, 11, 4), "taxa_aa": 14.75},
        {"Reuniao": "8/2026", "data_reuniao": date(2026, 12, 9), "taxa_aa": 14.50},
        {"Reuniao": "1/2027", "data_reuniao": date(2027, 1, 27), "taxa_aa": 14.25},
        {"Reuniao": "2/2027", "data_reuniao": date(2027, 3, 17), "taxa_aa": 14.00},
        {"Reuniao": "3/2027", "data_reuniao": date(2027, 5, 5),  "taxa_aa": 13.75},
        {"Reuniao": "4/2027", "data_reuniao": date(2027, 6, 16), "taxa_aa": 13.50},
        {"Reuniao": "5/2027", "data_reuniao": date(2027, 7, 28), "taxa_aa": 13.25},
        {"Reuniao": "6/2027", "data_reuniao": date(2027, 9, 15), "taxa_aa": 13.00},
        {"Reuniao": "7/2027", "data_reuniao": date(2027, 11, 3), "taxa_aa": 13.00},
        {"Reuniao": "8/2027", "data_reuniao": date(2027, 12, 8), "taxa_aa": 13.00},
    ]
    return pd.DataFrame(rows)


def get_focus_data_publicacao() -> str:
    """Retorna a data da publicação mais recente do Focus."""
    d = _get_latest_focus_date()
    return d if d else "N/D"
