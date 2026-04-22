"""
Integração com a API do Relatório Focus (Banco Central do Brasil).

IPCA mensal  → python-bcb: Expectativas / ExpectativaMercadoMensais
Selic/COPOM  → requests direto: ExpectativasMercadoSelic
               (endpoint não disponível no python-bcb)
"""
import requests
import pandas as pd
import streamlit as st
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

FOCUS_BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"

# Calendário oficial de reuniões COPOM (datas do último dia de cada reunião)
COPOM_DATES = {
    "1/2026": date(2026, 1, 29), "2/2026": date(2026, 3, 19),
    "3/2026": date(2026, 5, 7),  "4/2026": date(2026, 6, 18),
    "5/2026": date(2026, 7, 30), "6/2026": date(2026, 9, 17),
    "7/2026": date(2026, 11, 5), "8/2026": date(2026, 12, 10),
    "1/2027": date(2027, 1, 28), "2/2027": date(2027, 3, 18),
    "3/2027": date(2027, 5, 6),  "4/2027": date(2027, 6, 17),
    "5/2027": date(2027, 7, 29), "6/2027": date(2027, 9, 16),
    "7/2027": date(2027, 11, 4), "8/2027": date(2027, 12, 9),
    "1/2028": date(2028, 1, 27), "2/2028": date(2028, 3, 15),
    "3/2028": date(2028, 5, 4),  "4/2028": date(2028, 6, 15),
    "5/2028": date(2028, 7, 27), "6/2028": date(2028, 9, 14),
    "7/2028": date(2028, 11, 2), "8/2028": date(2028, 12, 7),
}


# ── IPCA ───────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 24)
def get_focus_ipca_mensal() -> pd.DataFrame:
    """
    Busca medianas mensais de IPCA do Focus, última publicação disponível.
    Usa python-bcb (biblioteca oficial). Fallback para requests direto.
    Retorna DataFrame: DataReferencia (Timestamp), Mediana (%), MesLabel (str)
    """
    df = _get_ipca_via_bcb()
    if df.empty:
        df = _get_ipca_via_requests()
    if df.empty:
        df = _focus_ipca_fallback()
    return df


def _get_ipca_via_bcb() -> pd.DataFrame:
    """Usa python-bcb para buscar IPCA mensal Focus."""
    try:
        from bcb import Expectativas
        em = Expectativas()
        ep = em.get_endpoint("ExpectativaMercadoMensais")

        # Busca a data da última publicação
        df_latest = (
            ep.query()
            .filter(ep.Indicador == "IPCA", ep.Suavizado == "N")
            .select("Data")
            .orderby("Data", ascending=False)
            .limit(1)
            .collect()
        )
        if df_latest.empty:
            return pd.DataFrame()

        ultima_data = df_latest.iloc[0]["Data"]
        if hasattr(ultima_data, "strftime"):
            ultima_str = ultima_data.strftime("%Y-%m-%d")
        else:
            ultima_str = str(ultima_data)[:10]

        # Busca todas as referências mensais da última publicação
        df = (
            ep.query()
            .filter(
                ep.Indicador == "IPCA",
                ep.Suavizado == "N",
                ep.Data == ultima_str,
            )
            .select("DataReferencia", "Mediana")
            .orderby("DataReferencia")
            .limit(60)
            .collect()
        )

        if df.empty:
            return pd.DataFrame()

        return _parse_ipca_df(df, ultima_str)

    except Exception:
        return pd.DataFrame()


def _get_ipca_via_requests() -> pd.DataFrame:
    """Fallback: busca IPCA via requests direto ao OData BCB."""
    try:
        # Última data de publicação
        url_last = (
            f"{FOCUS_BASE}/ExpectativaMercadoMensais"
            f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N'"
            f"&$top=1&$format=json&$select=Data&$orderby=Data desc"
        )
        r = requests.get(url_last, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        if r.status_code != 200:
            return pd.DataFrame()
        vals = r.json().get("value", [])
        if not vals:
            return pd.DataFrame()
        ultima = vals[0]["Data"]

        # Dados da última publicação
        url = (
            f"{FOCUS_BASE}/ExpectativaMercadoMensais"
            f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N' and Data eq '{ultima}'"
            f"&$top=60&$format=json&$select=DataReferencia,Mediana"
            f"&$orderby=DataReferencia asc"
        )
        r2 = requests.get(url, timeout=15,
                          headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        if r2.status_code != 200:
            return pd.DataFrame()

        return _parse_ipca_df(r2.json().get("value", []), ultima)

    except Exception:
        return pd.DataFrame()


def _parse_ipca_df(data, ultima_data: str) -> pd.DataFrame:
    """Normaliza dados de IPCA (aceita lista de dicts ou DataFrame)."""
    try:
        hoje = date.today().replace(day=1)
        rows = []

        if isinstance(data, pd.DataFrame):
            for _, row in data.iterrows():
                mes_raw = row.get("DataReferencia", "")
                mediana = row.get("Mediana")
                dt = _parse_mes_referencia(mes_raw)
                if dt and dt >= hoje and mediana is not None:
                    rows.append({
                        "DataReferencia": pd.Timestamp(dt),
                        "Mediana": float(mediana),
                        "MesLabel": dt.strftime("%m/%Y"),
                        "FocusData": ultima_data,
                    })
        else:  # lista de dicts
            for v in data:
                mes_raw = v.get("DataReferencia", "")
                mediana = v.get("Mediana")
                dt = _parse_mes_referencia(mes_raw)
                if dt and dt >= hoje and mediana is not None:
                    rows.append({
                        "DataReferencia": pd.Timestamp(dt),
                        "Mediana": float(mediana),
                        "MesLabel": dt.strftime("%m/%Y"),
                        "FocusData": ultima_data,
                    })

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).sort_values("DataReferencia").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def _parse_mes_referencia(mes_raw) -> date | None:
    """Converte DataReferencia para date. Aceita 'MM/YYYY' ou Timestamp."""
    try:
        if isinstance(mes_raw, (pd.Timestamp, datetime)):
            return mes_raw.date() if hasattr(mes_raw, "date") else mes_raw
        s = str(mes_raw).strip()
        if "/" in s and len(s) == 7:   # "MM/YYYY"
            return datetime.strptime(s, "%m/%Y").date()
        if "-" in s:                   # "YYYY-MM-DD" ou "YYYY-MM"
            return datetime.strptime(s[:7], "%Y-%m").date()
        return None
    except Exception:
        return None


def _focus_ipca_fallback() -> pd.DataFrame:
    """
    Fallback com valores do Focus de 17/04/2026.
    2026: valores mensais do print BCB.
    2027+: IPCA anual Focus convertido para mensal (média geométrica).
    """
    # Valores mensais 2026 conforme Focus 17/04/2026
    valores_2026 = {
        4: 0.6604, 5: 0.3700, 6: 0.3000, 7: 0.2461,
        8: 0.1300, 9: 0.3000, 10: 0.2400, 11: 0.2200, 12: 0.4151,
    }
    # IPCA anual Focus 17/04/2026: 2026≈5.65%, 2027≈4.40%, 2028≈4.00%
    # Mensal equivalente: (1 + anual)^(1/12) - 1
    ipca_anual = {2026: 5.65, 2027: 4.40, 2028: 4.00}
    def mensal_de_anual(ano):
        return ((1 + ipca_anual.get(ano, 4.00) / 100) ** (1/12) - 1) * 100

    rows = []
    ref = date.today().replace(day=1)
    for _ in range(36):
        if ref.year == 2026 and ref.month in valores_2026:
            v = valores_2026[ref.month]
        else:
            v = mensal_de_anual(ref.year)
        rows.append({
            "DataReferencia": pd.Timestamp(ref),
            "Mediana": round(v, 4),
            "MesLabel": ref.strftime("%m/%Y"),
            "FocusData": "fallback 17/04/2026",
        })
        ref += relativedelta(months=1)
    return pd.DataFrame(rows)


# ── SELIC ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 24)
def get_focus_selic_copom() -> pd.DataFrame:
    """
    Busca medianas de Selic por reunião COPOM (último Focus disponível).
    Usa requests direto pois ExpectativasMercadoSelic não está no python-bcb.
    Retorna DataFrame: Reuniao, data_reuniao, taxa_aa — ordenado por data.
    """
    df = _get_selic_via_requests()
    if df.empty:
        df = _focus_selic_fallback()
    return df


def _get_selic_via_requests() -> pd.DataFrame:
    """Busca Selic COPOM diretamente via OData BCB."""
    try:
        # Última data de publicação
        url_last = (
            f"{FOCUS_BASE}/ExpectativasMercadoSelic"
            f"?$top=1&$format=json&$select=Data&$orderby=Data desc"
        )
        r = requests.get(url_last, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        if r.status_code != 200:
            return pd.DataFrame()
        vals = r.json().get("value", [])
        if not vals:
            return pd.DataFrame()
        ultima = vals[0]["Data"]

        # Todos os dados da última publicação
        url = (
            f"{FOCUS_BASE}/ExpectativasMercadoSelic"
            f"?$filter=Data eq '{ultima}'"
            f"&$top=60&$format=json&$select=Reuniao,Mediana"
            f"&$orderby=Reuniao asc"
        )
        r2 = requests.get(url, timeout=15,
                          headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        if r2.status_code != 200:
            return pd.DataFrame()

        return _parse_selic_df(r2.json().get("value", []))

    except Exception:
        return pd.DataFrame()


def _parse_selic_df(vals: list) -> pd.DataFrame:
    """Normaliza dados de Selic COPOM."""
    rows = []
    seen = set()
    for v in vals:
        reuniao = str(v.get("Reuniao", "")).strip()
        mediana = v.get("Mediana")
        if not reuniao or mediana is None or reuniao in seen:
            continue
        seen.add(reuniao)
        dt = COPOM_DATES.get(reuniao) or _parse_reuniao_to_date(reuniao)
        if dt is None:
            continue
        rows.append({"Reuniao": reuniao, "data_reuniao": dt, "taxa_aa": float(mediana)})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values("data_reuniao").reset_index(drop=True)
    return df[df["data_reuniao"] >= date.today()].reset_index(drop=True)


def _parse_reuniao_to_date(reuniao: str) -> date | None:
    try:
        num, ano = int(reuniao.split("/")[0]), int(reuniao.split("/")[1])
        mapa = {1: 1, 2: 3, 3: 5, 4: 6, 5: 7, 6: 9, 7: 11, 8: 12}
        return date(ano, mapa.get(num, 6), 15)
    except Exception:
        return None


def _focus_selic_fallback() -> pd.DataFrame:
    """
    Fallback com valores do Focus de 17/04/2026 (prints do BCB):
    R3=14.50, R4=14.25, R5=13.75, R6=13.25, R7=13.00, R8=13.00
    """
    rows = [
        {"Reuniao": "3/2026",  "data_reuniao": COPOM_DATES["3/2026"],  "taxa_aa": 14.50},
        {"Reuniao": "4/2026",  "data_reuniao": COPOM_DATES["4/2026"],  "taxa_aa": 14.25},
        {"Reuniao": "5/2026",  "data_reuniao": COPOM_DATES["5/2026"],  "taxa_aa": 13.75},
        {"Reuniao": "6/2026",  "data_reuniao": COPOM_DATES["6/2026"],  "taxa_aa": 13.25},
        {"Reuniao": "7/2026",  "data_reuniao": COPOM_DATES["7/2026"],  "taxa_aa": 13.00},
        {"Reuniao": "8/2026",  "data_reuniao": COPOM_DATES["8/2026"],  "taxa_aa": 13.00},
        {"Reuniao": "1/2027",  "data_reuniao": COPOM_DATES["1/2027"],  "taxa_aa": 12.75},
        {"Reuniao": "2/2027",  "data_reuniao": COPOM_DATES["2/2027"],  "taxa_aa": 12.50},
        {"Reuniao": "3/2027",  "data_reuniao": COPOM_DATES["3/2027"],  "taxa_aa": 12.25},
        {"Reuniao": "4/2027",  "data_reuniao": COPOM_DATES["4/2027"],  "taxa_aa": 12.00},
        {"Reuniao": "5/2027",  "data_reuniao": COPOM_DATES["5/2027"],  "taxa_aa": 12.00},
        {"Reuniao": "6/2027",  "data_reuniao": COPOM_DATES["6/2027"],  "taxa_aa": 12.00},
        {"Reuniao": "7/2027",  "data_reuniao": COPOM_DATES["7/2027"],  "taxa_aa": 12.00},
        {"Reuniao": "8/2027",  "data_reuniao": COPOM_DATES["8/2027"],  "taxa_aa": 12.00},
    ]
    return pd.DataFrame(rows)


# ── Utilitários ────────────────────────────────────────────────────────────────

def get_focus_data_publicacao() -> str:
    """Retorna a data da última publicação do Focus (IPCA)."""
    try:
        url = (f"{FOCUS_BASE}/ExpectativaMercadoMensais"
               f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N'"
               f"&$top=1&$format=json&$select=Data&$orderby=Data desc")
        r = requests.get(url, timeout=10,
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        if r.status_code == 200:
            v = r.json().get("value", [])
            if v:
                return v[0]["Data"]
    except Exception:
        pass
    return "N/D"
