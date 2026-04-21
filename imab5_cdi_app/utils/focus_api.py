"""
Integração com a API do Relatório Focus (Banco Central do Brasil).
Busca projeções de IPCA mensal e Selic por reunião do COPOM.
"""
import requests
import pandas as pd
import streamlit as st
from datetime import date, datetime
import json


FOCUS_BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"


@st.cache_data(ttl=3600 * 6)  # cache de 6 horas
def get_focus_ipca_mensal() -> pd.DataFrame:
    """
    Busca projeções mensais de IPCA do Focus (mediana).
    Retorna DataFrame com colunas: DataReferencia, Mediana
    """
    try:
        today = date.today().strftime("%Y-%m-%d")
        url = (
            f"{FOCUS_BASE}/ExpectativaMercadoMensais"
            f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N' and Data eq '{today}'"
            f"&$top=36&$format=json&$select=Indicador,Data,DataReferencia,Mediana"
            f"&$orderby=DataReferencia asc"
        )
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            # Tenta com a data mais recente disponível
            return _get_focus_ipca_latest()
        data = resp.json().get("value", [])
        if not data:
            return _get_focus_ipca_latest()
        df = pd.DataFrame(data)
        df["DataReferencia"] = pd.to_datetime(df["DataReferencia"], format="%m/%Y")
        df = df[["DataReferencia", "Mediana"]].dropna()
        df = df[df["DataReferencia"] >= pd.Timestamp(date.today().replace(day=1))]
        df = df.sort_values("DataReferencia").reset_index(drop=True)
        return df
    except Exception as e:
        return _get_focus_ipca_latest()


def _get_focus_ipca_latest() -> pd.DataFrame:
    """Busca IPCA Focus da publicação mais recente disponível."""
    try:
        url = (
            f"{FOCUS_BASE}/ExpectativaMercadoMensais"
            f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N'"
            f"&$top=1&$format=json&$select=Data&$orderby=Data desc"
        )
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return _focus_ipca_fallback()
        latest = resp.json().get("value", [{}])[0].get("Data", "")
        if not latest:
            return _focus_ipca_fallback()

        url2 = (
            f"{FOCUS_BASE}/ExpectativaMercadoMensais"
            f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N' and Data eq '{latest}'"
            f"&$top=36&$format=json&$select=Indicador,Data,DataReferencia,Mediana"
            f"&$orderby=DataReferencia asc"
        )
        resp2 = requests.get(url2, timeout=15)
        if resp2.status_code != 200:
            return _focus_ipca_fallback()
        data = resp2.json().get("value", [])
        if not data:
            return _focus_ipca_fallback()
        df = pd.DataFrame(data)
        df["DataReferencia"] = pd.to_datetime(df["DataReferencia"], format="%m/%Y")
        df = df[["DataReferencia", "Mediana"]].dropna()
        df = df[df["DataReferencia"] >= pd.Timestamp(date.today().replace(day=1))]
        df = df.sort_values("DataReferencia").reset_index(drop=True)
        return df
    except Exception:
        return _focus_ipca_fallback()


def _focus_ipca_fallback() -> pd.DataFrame:
    """Valores padrão caso API esteja indisponível."""
    from dateutil.relativedelta import relativedelta
    rows = []
    ref = date.today().replace(day=1)
    default_ipca = 0.35
    for i in range(24):
        rows.append({"DataReferencia": pd.Timestamp(ref), "Mediana": default_ipca})
        ref = (ref + relativedelta(months=1))
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600 * 6)
def get_focus_selic_copom() -> pd.DataFrame:
    """
    Busca projeções de Selic por reunião do COPOM do Focus (mediana).
    Retorna DataFrame com colunas: DataReferencia (data da reunião), Mediana (taxa a.a.)
    """
    try:
        today = date.today().strftime("%Y-%m-%d")
        url = (
            f"{FOCUS_BASE}/ExpectativasMercadoSelic"
            f"?$filter=Data eq '{today}'"
            f"&$top=40&$format=json&$select=Data,Reuniao,Mediana"
            f"&$orderby=Reuniao asc"
        )
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return _get_focus_selic_latest()
        data = resp.json().get("value", [])
        if not data:
            return _get_focus_selic_latest()
        df = pd.DataFrame(data)
        df = df[["Reuniao", "Mediana"]].dropna()
        return df.reset_index(drop=True)
    except Exception:
        return _get_focus_selic_latest()


def _get_focus_selic_latest() -> pd.DataFrame:
    """Busca Selic Focus da publicação mais recente."""
    try:
        url = (
            f"{FOCUS_BASE}/ExpectativasMercadoSelic"
            f"?$top=1&$format=json&$select=Data&$orderby=Data desc"
        )
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return _focus_selic_fallback()
        latest = resp.json().get("value", [{}])[0].get("Data", "")
        if not latest:
            return _focus_selic_fallback()
        url2 = (
            f"{FOCUS_BASE}/ExpectativasMercadoSelic"
            f"?$filter=Data eq '{latest}'"
            f"&$top=40&$format=json&$select=Data,Reuniao,Mediana"
            f"&$orderby=Reuniao asc"
        )
        resp2 = requests.get(url2, timeout=15)
        if resp2.status_code != 200:
            return _focus_selic_fallback()
        data = resp2.json().get("value", [])
        if not data:
            return _focus_selic_fallback()
        df = pd.DataFrame(data)
        df = df[["Reuniao", "Mediana"]].dropna()
        return df.reset_index(drop=True)
    except Exception:
        return _focus_selic_fallback()


def _focus_selic_fallback() -> pd.DataFrame:
    """Valores padrão para Selic caso API indisponível."""
    rows = [
        {"Reuniao": "1/2026", "Mediana": 14.75},
        {"Reuniao": "2/2026", "Mediana": 15.00},
        {"Reuniao": "3/2026", "Mediana": 15.00},
        {"Reuniao": "4/2026", "Mediana": 14.75},
        {"Reuniao": "5/2026", "Mediana": 14.50},
        {"Reuniao": "6/2026", "Mediana": 14.25},
        {"Reuniao": "1/2027", "Mediana": 13.75},
        {"Reuniao": "2/2027", "Mediana": 13.50},
    ]
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600 * 6)
def get_focus_ipca_anual() -> pd.DataFrame:
    """
    Busca projeções anuais de IPCA para os próximos 2 anos (mediana Focus).
    """
    try:
        today = date.today().strftime("%Y-%m-%d")
        anos = [str(date.today().year), str(date.today().year + 1), str(date.today().year + 2)]
        dfs = []
        for ano in anos:
            url = (
                f"{FOCUS_BASE}/ExpectativaMercadoAnuais"
                f"?$filter=Indicador eq 'IPCA' and Data eq '{today}' and DataReferencia eq '{ano}'"
                f"&$top=1&$format=json&$select=DataReferencia,Mediana"
            )
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("value", [])
                if data:
                    dfs.append({"Ano": int(ano), "Mediana": data[0].get("Mediana", 4.0)})
        if dfs:
            return pd.DataFrame(dfs)
    except Exception:
        pass
    return pd.DataFrame([
        {"Ano": date.today().year, "Mediana": 5.5},
        {"Ano": date.today().year + 1, "Mediana": 4.5},
        {"Ano": date.today().year + 2, "Mediana": 4.0},
    ])


def get_focus_data_publicacao() -> str:
    """Retorna a data da publicação mais recente do Focus."""
    try:
        url = (
            f"{FOCUS_BASE}/ExpectativaMercadoMensais"
            f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N'"
            f"&$top=1&$format=json&$select=Data&$orderby=Data desc"
        )
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("value", [])
            if data:
                return data[0].get("Data", "N/D")
    except Exception:
        pass
    return "N/D"
