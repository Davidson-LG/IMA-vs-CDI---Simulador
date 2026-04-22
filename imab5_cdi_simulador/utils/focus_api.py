"""
API Focus (BCB) — IPCA mensal + Selic COPOM.

IPCA:
  - Meses disponíveis (~12-18 à frente): ExpectativaMercadoMensais
  - Anos além disso (2027+): ExpectativasMercadoAnuais → convertido para mensal
Selic: ExpectativasMercadoSelic (requests direto, não está no python-bcb)
"""
import requests
import pandas as pd
import streamlit as st
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

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


def _get(url: str) -> list:
    """GET request → lista de registros ou []."""
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        if r.status_code == 200:
            return r.json().get("value", [])
    except Exception:
        pass
    return []


def _latest_date(endpoint: str, indicador: str = "IPCA", suavizado: str = "N") -> str | None:
    """Retorna a data da publicação mais recente para o endpoint."""
    filt = f"Indicador eq '{indicador}'"
    if suavizado:
        filt += f" and Suavizado eq '{suavizado}'"
    url = f"{BASE}/{endpoint}?$filter={filt}&$top=1&$format=json&$select=Data&$orderby=Data desc"
    vals = _get(url)
    return vals[0]["Data"] if vals else None


# ── IPCA ───────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 24)
def get_focus_ipca_mensal() -> pd.DataFrame:
    """
    Retorna medianas mensais de IPCA do Focus, da data atual até ~3 anos à frente.
    Combina dados mensais (ExpectativaMercadoMensais) com anuais (ExpectativasMercadoAnuais)
    para cobrir 2027 e além.
    """
    hoje = date.today().replace(day=1)

    # 1. Busca dados mensais do Focus
    mensal_map = _fetch_ipca_mensal()   # {date: mediana%}

    # 2. Busca dados anuais do Focus para preencher lacunas
    anual_map  = _fetch_ipca_anual()    # {ano: mediana%}

    # 3. Monta série completa para os próximos 36 meses
    rows = []
    ref = hoje
    for _ in range(36):
        if ref in mensal_map:
            v = mensal_map[ref]
        elif ref.year in anual_map:
            # Converte IPCA anual em mensal equivalente
            v = round(((1 + anual_map[ref.year] / 100) ** (1/12) - 1) * 100, 4)
        else:
            v = 0.30  # último fallback
        rows.append({
            "DataReferencia": pd.Timestamp(ref),
            "Mediana": v,
            "MesLabel": ref.strftime("%m/%Y"),
        })
        ref += relativedelta(months=1)

    df = pd.DataFrame(rows)
    return df if not df.empty else _focus_ipca_fallback()


def _fetch_ipca_mensal() -> dict:
    """Busca medianas mensais de IPCA. Retorna {date: mediana%}."""
    # Tenta python-bcb primeiro
    result = _ipca_mensal_via_bcb()
    if result:
        return result
    # Fallback: requests direto
    return _ipca_mensal_via_requests()


def _ipca_mensal_via_bcb() -> dict:
    try:
        from bcb import Expectativas
        em = Expectativas()
        ep = em.get_endpoint("ExpectativaMercadoMensais")
        # Última data de publicação
        df_last = (ep.query()
                   .filter(ep.Indicador == "IPCA", ep.Suavizado == "N")
                   .select("Data").orderby("Data", ascending=False).limit(1).collect())
        if df_last.empty:
            return {}
        ultima = str(df_last.iloc[0]["Data"])[:10]
        df = (ep.query()
              .filter(ep.Indicador == "IPCA", ep.Suavizado == "N", ep.Data == ultima)
              .select("DataReferencia", "Mediana")
              .orderby("DataReferencia").limit(60).collect())
        if df.empty:
            return {}
        return _parse_mensal_list(df.to_dict("records"))
    except Exception:
        return {}


def _ipca_mensal_via_requests() -> dict:
    ultima = _latest_date("ExpectativaMercadoMensais")
    if not ultima:
        return {}
    url = (f"{BASE}/ExpectativaMercadoMensais"
           f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N' and Data eq '{ultima}'"
           f"&$top=60&$format=json&$select=DataReferencia,Mediana&$orderby=DataReferencia asc")
    return _parse_mensal_list(_get(url))


def _parse_mensal_list(records) -> dict:
    """Converte lista de registros em {date: mediana%}."""
    result = {}
    hoje = date.today().replace(day=1)
    for v in records:
        mes = v.get("DataReferencia", "")
        med = v.get("Mediana")
        if med is None:
            continue
        dt = _parse_mes(mes)
        if dt and dt >= hoje:
            result[dt] = float(med)
    return result


def _fetch_ipca_anual() -> dict:
    """Busca medianas anuais de IPCA. Retorna {ano: mediana%}."""
    result = _ipca_anual_via_bcb()
    if result:
        return result
    return _ipca_anual_via_requests()


def _ipca_anual_via_bcb() -> dict:
    try:
        from bcb import Expectativas
        em = Expectativas()
        ep = em.get_endpoint("ExpectativasMercadoAnuais")
        df_last = (ep.query()
                   .filter(ep.Indicador == "IPCA")
                   .select("Data").orderby("Data", ascending=False).limit(1).collect())
        if df_last.empty:
            return {}
        ultima = str(df_last.iloc[0]["Data"])[:10]
        ano_atual = date.today().year
        df = (ep.query()
              .filter(ep.Indicador == "IPCA", ep.Data == ultima)
              .select("DataReferencia", "Mediana")
              .orderby("DataReferencia").limit(10).collect())
        if df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            try:
                ano = int(str(row["DataReferencia"])[:4])
                if ano >= ano_atual:
                    result[ano] = float(row["Mediana"])
            except Exception:
                pass
        return result
    except Exception:
        return {}


def _ipca_anual_via_requests() -> dict:
    # Última data para anuais
    try:
        url_last = (f"{BASE}/ExpectativasMercadoAnuais"
                    f"?$filter=Indicador eq 'IPCA'&$top=1&$format=json"
                    f"&$select=Data&$orderby=Data desc")
        vals = _get(url_last)
        if not vals:
            return {}
        ultima = vals[0]["Data"]
        ano_atual = date.today().year
        url = (f"{BASE}/ExpectativasMercadoAnuais"
               f"?$filter=Indicador eq 'IPCA' and Data eq '{ultima}'"
               f"&$top=10&$format=json&$select=DataReferencia,Mediana"
               f"&$orderby=DataReferencia asc")
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
    except Exception:
        return {}


def _parse_mes(mes_raw) -> date | None:
    try:
        if isinstance(mes_raw, (pd.Timestamp, datetime)):
            d = mes_raw if isinstance(mes_raw, date) else mes_raw.date()
            return d.replace(day=1)
        s = str(mes_raw).strip()
        if "/" in s and len(s) == 7:
            return datetime.strptime(s, "%m/%Y").date()
        if "-" in s:
            return datetime.strptime(s[:7], "%Y-%m").date()
    except Exception:
        pass
    return None


def _focus_ipca_fallback() -> pd.DataFrame:
    """
    Fallback Focus 17/04/2026.
    2026 mensal: valores do print BCB.
    2027: 4.40% anual → 0.3595% mensal.
    2028: 4.00% anual → 0.3274% mensal.
    """
    m2026 = {4:0.6604, 5:0.3700, 6:0.3000, 7:0.2461,
              8:0.1300, 9:0.3000, 10:0.2400, 11:0.2200, 12:0.4151}
    anual = {2026:5.65, 2027:4.40, 2028:4.00}
    def to_mensal(a): return round(((1 + anual.get(a,4.0)/100)**(1/12)-1)*100, 4)
    rows, ref = [], date.today().replace(day=1)
    for _ in range(36):
        v = (m2026[ref.month] if ref.year==2026 and ref.month in m2026
             else to_mensal(ref.year))
        rows.append({"DataReferencia":pd.Timestamp(ref), "Mediana":v,
                     "MesLabel":ref.strftime("%m/%Y")})
        ref += relativedelta(months=1)
    return pd.DataFrame(rows)


# ── SELIC ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 24)
def get_focus_selic_copom() -> pd.DataFrame:
    df = _selic_via_requests()
    return df if not df.empty else _focus_selic_fallback()


def _selic_via_requests() -> pd.DataFrame:
    url_last = f"{BASE}/ExpectativasMercadoSelic?$top=1&$format=json&$select=Data&$orderby=Data desc"
    vals = _get(url_last)
    if not vals:
        return pd.DataFrame()
    ultima = vals[0]["Data"]
    url = (f"{BASE}/ExpectativasMercadoSelic"
           f"?$filter=Data eq '{ultima}'"
           f"&$top=60&$format=json&$select=Reuniao,Mediana&$orderby=Reuniao asc")
    rows, seen = [], set()
    for v in _get(url):
        reuniao = str(v.get("Reuniao","")).strip()
        med = v.get("Mediana")
        if not reuniao or med is None or reuniao in seen:
            continue
        seen.add(reuniao)
        dt = COPOM_DATES.get(reuniao) or _parse_reuniao(reuniao)
        if dt and dt >= date.today():
            rows.append({"Reuniao":reuniao, "data_reuniao":dt, "taxa_aa":float(med)})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("data_reuniao").reset_index(drop=True)


def _parse_reuniao(r: str) -> date | None:
    try:
        n, a = int(r.split("/")[0]), int(r.split("/")[1])
        m = {1:1,2:3,3:5,4:6,5:7,6:9,7:11,8:12}.get(n,6)
        return date(a, m, 15)
    except Exception:
        return None


def _focus_selic_fallback() -> pd.DataFrame:
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


def get_focus_data_publicacao() -> str:
    d = _latest_date("ExpectativaMercadoMensais")
    return d if d else "N/D"
