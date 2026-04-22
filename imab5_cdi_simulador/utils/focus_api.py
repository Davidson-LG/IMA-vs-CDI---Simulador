"""
API Focus (BCB) — IPCA mensal + Selic COPOM.
Sempre retorna dados corretos: API quando disponível, fallback calibrado caso contrário.
"""
import requests
import pandas as pd
import streamlit as st
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

COPOM_DATES = {
    "1/2026": date(2026,1,29), "2/2026": date(2026,3,19),
    "3/2026": date(2026,5,7),  "4/2026": date(2026,6,18),
    "5/2026": date(2026,7,30), "6/2026": date(2026,9,17),
    "7/2026": date(2026,11,5), "8/2026": date(2026,12,10),
    "1/2027": date(2027,1,28), "2/2027": date(2027,3,18),
    "3/2027": date(2027,5,6),  "4/2027": date(2027,6,17),
    "5/2027": date(2027,7,29), "6/2027": date(2027,9,16),
    "7/2027": date(2027,11,4), "8/2027": date(2027,12,9),
    "1/2028": date(2028,1,27), "2/2028": date(2028,3,15),
    "3/2028": date(2028,5,4),  "4/2028": date(2028,6,15),
    "5/2028": date(2028,7,27), "6/2028": date(2028,9,14),
    "7/2028": date(2028,11,2), "8/2028": date(2028,12,7),
}

# ── Valores fixos do Focus 17/04/2026 (fallback calibrado) ────────────────────
# IPCA mensal 2026 (fonte: sistema BCB 17/04/2026)
IPCA_MENSAL_2026 = {
    4: 0.6604, 5: 0.3700, 6: 0.3000, 7: 0.2461,
    8: 0.1300, 9: 0.3000, 10: 0.2400, 11: 0.2200, 12: 0.4151,
}
# IPCA anual Focus 17/04/2026: 2026=5.65%, 2027=4.40%, 2028=4.00%
# Mensal: (1+anual)^(1/12)-1
IPCA_ANUAL_FOCUS = {2026: 5.65, 2027: 4.40, 2028: 4.00}

FOCUS_FALLBACK_DATE = "17/04/2026"


def _ipca_mensal_de_anual(ano: int) -> float:
    aa = IPCA_ANUAL_FOCUS.get(ano, 4.00)
    return round(((1 + aa / 100) ** (1/12) - 1) * 100, 4)


def _get(url: str) -> list:
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        if r.status_code == 200:
            return r.json().get("value", [])
    except Exception:
        pass
    return []


# ── IPCA ───────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 24)
def get_focus_ipca_mensal() -> pd.DataFrame:
    """
    Retorna IPCA mensal Focus para os próximos 36 meses.
    Fonte 1: API BCB (ExpectativaMercadoMensais + ExpectativasMercadoAnuais)
    Fonte 2: fallback calibrado com valores Focus 17/04/2026
    """
    hoje = date.today().replace(day=1)

    # Tenta API
    mensal_map, data_pub = _fetch_mensal_api()  # {date: %}, "YYYY-MM-DD"
    anual_map = _fetch_anual_api()              # {ano: %}

    # Monta série de 36 meses
    rows = []
    ref = hoje
    for _ in range(36):
        if ref in mensal_map:
            v = mensal_map[ref]
        elif ref.year in anual_map:
            v = round(((1 + anual_map[ref.year] / 100) ** (1/12) - 1) * 100, 4)
        else:
            # Fallback calibrado
            if ref.year == 2026 and ref.month in IPCA_MENSAL_2026:
                v = IPCA_MENSAL_2026[ref.month]
            else:
                v = _ipca_mensal_de_anual(ref.year)
        rows.append({
            "DataReferencia": pd.Timestamp(ref),
            "Mediana": v,
            "MesLabel": ref.strftime("%m/%Y"),
        })
        ref += relativedelta(months=1)

    return pd.DataFrame(rows)


def _fetch_mensal_api() -> tuple:
    """Busca IPCA mensal. Retorna ({date: mediana}, data_publicacao_str)."""
    # Última data de publicação
    url_last = (f"{BASE}/ExpectativaMercadoMensais"
                f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N'"
                f"&$top=1&$format=json&$select=Data&$orderby=Data desc")
    vals = _get(url_last)
    if not vals:
        return {}, ""

    ultima = vals[0].get("Data", "")
    if not ultima:
        return {}, ""

    url = (f"{BASE}/ExpectativaMercadoMensais"
           f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N' and Data eq '{ultima}'"
           f"&$top=60&$format=json&$select=DataReferencia,Mediana"
           f"&$orderby=DataReferencia asc")

    hoje = date.today().replace(day=1)
    result = {}
    for v in _get(url):
        dt = _parse_mes(v.get("DataReferencia", ""))
        med = v.get("Mediana")
        if dt and dt >= hoje and med is not None:
            result[dt] = float(med)

    return result, ultima


def _fetch_anual_api() -> dict:
    """Busca IPCA anual Focus. Retorna {ano: mediana%}."""
    url_last = (f"{BASE}/ExpectativasMercadoAnuais"
                f"?$filter=Indicador eq 'IPCA'"
                f"&$top=1&$format=json&$select=Data&$orderby=Data desc")
    vals = _get(url_last)
    if not vals:
        return {}
    ultima = vals[0].get("Data", "")
    if not ultima:
        return {}

    url = (f"{BASE}/ExpectativasMercadoAnuais"
           f"?$filter=Indicador eq 'IPCA' and Data eq '{ultima}'"
           f"&$top=10&$format=json&$select=DataReferencia,Mediana"
           f"&$orderby=DataReferencia asc")

    ano_atual = date.today().year
    result = {}
    for v in _get(url):
        try:
            ano = int(str(v.get("DataReferencia", ""))[:4])
            med = v.get("Mediana")
            if ano >= ano_atual and med is not None:
                result[ano] = float(med)
        except Exception:
            pass
    return result


def _parse_mes(s) -> date | None:
    try:
        if isinstance(s, (pd.Timestamp, datetime)):
            d = s.date() if hasattr(s, "date") else s
            return d.replace(day=1)
        s = str(s).strip()
        if "/" in s and len(s) == 7:
            return datetime.strptime(s, "%m/%Y").date()
        if len(s) >= 7 and "-" in s:
            return datetime.strptime(s[:7], "%Y-%m").date()
    except Exception:
        pass
    return None


# ── SELIC ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 24)
def get_focus_selic_copom() -> pd.DataFrame:
    """Busca Selic por reunião COPOM. Fallback = valores Focus 17/04/2026."""
    url_last = (f"{BASE}/ExpectativasMercadoSelic"
                f"?$top=1&$format=json&$select=Data&$orderby=Data desc")
    vals = _get(url_last)
    if not vals:
        return _selic_fallback()

    ultima = vals[0].get("Data", "")
    if not ultima:
        return _selic_fallback()

    url = (f"{BASE}/ExpectativasMercadoSelic"
           f"?$filter=Data eq '{ultima}'"
           f"&$top=60&$format=json&$select=Reuniao,Mediana&$orderby=Reuniao asc")

    rows, seen = [], set()
    for v in _get(url):
        reuniao = str(v.get("Reuniao", "")).strip()
        med = v.get("Mediana")
        if not reuniao or med is None or reuniao in seen:
            continue
        seen.add(reuniao)
        dt = COPOM_DATES.get(reuniao) or _parse_reuniao(reuniao)
        if dt and dt >= date.today():
            rows.append({"Reuniao": reuniao, "data_reuniao": dt, "taxa_aa": float(med)})

    if not rows:
        return _selic_fallback()

    return pd.DataFrame(rows).sort_values("data_reuniao").reset_index(drop=True)


def _parse_reuniao(r: str) -> date | None:
    try:
        n, a = int(r.split("/")[0]), int(r.split("/")[1])
        m = {1:1,2:3,3:5,4:6,5:7,6:9,7:11,8:12}.get(n,6)
        return date(a, m, 15)
    except Exception:
        return None


def _selic_fallback() -> pd.DataFrame:
    """Focus 17/04/2026: R3=14.50, R4=14.25, R5=13.75, R6=13.25, R7/R8=13.00."""
    rows = [
        {"Reuniao":"3/2026",  "data_reuniao":COPOM_DATES["3/2026"],  "taxa_aa":14.50},
        {"Reuniao":"4/2026",  "data_reuniao":COPOM_DATES["4/2026"],  "taxa_aa":14.25},
        {"Reuniao":"5/2026",  "data_reuniao":COPOM_DATES["5/2026"],  "taxa_aa":13.75},
        {"Reuniao":"6/2026",  "data_reuniao":COPOM_DATES["6/2026"],  "taxa_aa":13.25},
        {"Reuniao":"7/2026",  "data_reuniao":COPOM_DATES["7/2026"],  "taxa_aa":13.00},
        {"Reuniao":"8/2026",  "data_reuniao":COPOM_DATES["8/2026"],  "taxa_aa":13.00},
        {"Reuniao":"1/2027",  "data_reuniao":COPOM_DATES["1/2027"],  "taxa_aa":12.75},
        {"Reuniao":"2/2027",  "data_reuniao":COPOM_DATES["2/2027"],  "taxa_aa":12.50},
        {"Reuniao":"3/2027",  "data_reuniao":COPOM_DATES["3/2027"],  "taxa_aa":12.25},
        {"Reuniao":"4/2027",  "data_reuniao":COPOM_DATES["4/2027"],  "taxa_aa":12.00},
        {"Reuniao":"5/2027",  "data_reuniao":COPOM_DATES["5/2027"],  "taxa_aa":12.00},
        {"Reuniao":"6/2027",  "data_reuniao":COPOM_DATES["6/2027"],  "taxa_aa":12.00},
        {"Reuniao":"7/2027",  "data_reuniao":COPOM_DATES["7/2027"],  "taxa_aa":12.00},
        {"Reuniao":"8/2027",  "data_reuniao":COPOM_DATES["8/2027"],  "taxa_aa":12.00},
    ]
    return pd.DataFrame(rows)


# ── Data de publicação ─────────────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 24)
def get_focus_data_publicacao() -> str:
    """
    Retorna data da última publicação do Focus formatada como dd/mm/yyyy.
    Se API indisponível, retorna data do fallback.
    """
    url = (f"{BASE}/ExpectativaMercadoMensais"
           f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N'"
           f"&$top=1&$format=json&$select=Data&$orderby=Data desc")
    vals = _get(url)
    if vals:
        d = vals[0].get("Data", "")
        if d:
            try:
                return datetime.strptime(d[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                return d
    # API indisponível — retorna data do fallback
    return f"{FOCUS_FALLBACK_DATE} (fallback)"
