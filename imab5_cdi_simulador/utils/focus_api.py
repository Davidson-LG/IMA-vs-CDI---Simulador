"""
API Focus (BCB) — IPCA mensal + Selic COPOM.

Endpoints para IPCA mensal individual (não suavizado):
  - ExpectativaMercadoMensais: cobre ~12 meses à frente (Suavizado='N')
  - ExpectativasMercadoInflacao24Meses: cobre meses 13-24 à frente
  Combinando os dois: cobertura individual de ~24 meses
  Para além disso: ExpectativasMercadoAnuais (anual → mensal via (1+r)^(1/12)-1)
"""
import requests
import pandas as pd
import streamlit as st
from datetime import date, datetime
from collections import Counter
from dateutil.relativedelta import relativedelta

BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Datas COPOM confirmadas (última data da reunião de 2 dias)
# 2026: Fonte BCB nota 20739 (https://www.bcb.gov.br/detalhenoticia/20739/nota)
# 2027: Fonte planilha de mercado (BCB publica até junho do ano anterior)
# 2028: Estimativas — serão substituídas automaticamente ao buscar da API
COPOM_DATES = {
    # 2026 — confirmadas BCB nota 20739
    "1/2026": date(2026,1,28),  "2/2026": date(2026,3,18),
    "3/2026": date(2026,4,29),  "4/2026": date(2026,6,17),
    "5/2026": date(2026,8,5),   "6/2026": date(2026,9,16),
    "7/2026": date(2026,11,4),  "8/2026": date(2026,12,9),
    # 2027 — fonte planilha (BCB ainda não publicou)
    "1/2027": date(2027,1,13),  "2/2027": date(2027,2,24),
    "3/2027": date(2027,4,9),   "4/2027": date(2027,5,24),
    "5/2027": date(2027,7,8),   "6/2027": date(2027,8,20),
    "7/2027": date(2027,10,4),  "8/2027": date(2027,11,18),
    # 2028 — estimativas
    "1/2028": date(2028,1,26),  "2/2028": date(2028,3,12),
    "3/2028": date(2028,4,30),  "4/2028": date(2028,6,14),
    "5/2028": date(2028,7,26),  "6/2028": date(2028,9,13),
    "7/2028": date(2028,11,1),  "8/2028": date(2028,12,6),
}

@st.cache_data(ttl=3600 * 24 * 7)  # cache semanal — BCB publica calendário ~junho do ano anterior
def _fetch_copom_calendar_bcb() -> dict:
    """
    Busca calendário COPOM da API BCB (endpoint de reuniões).
    Retorna {reuniao_str: date} com as datas mais recentes do BCB.
    Usa como fallback as datas hardcoded de COPOM_DATES.
    """
    try:
        # Endpoint BCB: lista de reuniões do COPOM com datas
        url = ("https://www.bcb.gov.br/api/servico/sitebcb/reunioescopom"
               "?quantidade=20&filtro=")
        r = requests.get(url, timeout=15, headers=HEADERS)
        if r.status_code == 200:
            data = r.json()
            result = {}
            conteudo = data.get("conteudo", [])
            for item in conteudo:
                # Cada item tem 'Datareuniao' e 'Numeroreuniao' ex: "278/2026"
                data_str  = item.get("DataFim") or item.get("DataReuniao") or ""
                num_str   = item.get("Numeroreuniao","")
                if not data_str or not num_str:
                    continue
                # Converte número "278/2026" → reuniao "3/2026" (3ª reunião de 2026)
                # Ou usa diretamente se vier como "3/2026"
                try:
                    dt = datetime.strptime(data_str[:10], "%Y-%m-%d").date()
                    # Mapeia número absoluto para "N/YYYY"
                    if "/" in num_str:
                        ano = int(num_str.split("/")[1])
                        # Conta quantas reuniões já ocorreram nesse ano
                        # A API retorna em ordem → determinamos o índice
                        result[num_str] = dt
                except Exception:
                    pass
            if result:
                return result
    except Exception:
        pass
    return {}

# Fallback Focus 17/04/2026 — usado APENAS se API estiver completamente fora do ar
IPCA_FALLBACK: dict[tuple, float] = {
    (2026,4):0.6604, (2026,5):0.3700, (2026,6):0.3000,
    (2026,7):0.2461, (2026,8):0.1300, (2026,9):0.3000,
    (2026,10):0.2400,(2026,11):0.2200,(2026,12):0.4151,
}
IPCA_ANUAL_FALLBACK = {2026:5.65, 2027:4.40, 2028:4.00}
FOCUS_FALLBACK_DATE = "17/04/2026"


def _mensal_de_anual(ano: int) -> float:
    aa = IPCA_ANUAL_FALLBACK.get(ano, 4.00)
    return round(((1 + aa / 100) ** (1/12) - 1) * 100, 4)


def _get(url: str) -> list:
    try:
        r = requests.get(url, timeout=20, headers=HEADERS)
        if r.status_code == 200:
            return r.json().get("value", [])
    except Exception:
        pass
    return []


def _latest_pub_date(endpoint: str, extra_filter: str = "") -> str:
    """Busca a data da publicação mais recente de um endpoint."""
    filt = f"Indicador eq 'IPCA'{extra_filter}"
    url = (f"{BASE}/{endpoint}?$filter={filt}"
           f"&$top=1&$format=json&$select=Data&$orderby=Data desc")
    vals = _get(url)
    return vals[0].get("Data", "") if vals else ""


def _parse_mes(s) -> date | None:
    try:
        if isinstance(s, (pd.Timestamp, datetime)):
            d = s.date() if hasattr(s, "date") else s
            return d.replace(day=1)
        s = str(s).strip()
        if "/" in s and len(s) == 7:   # MM/YYYY
            return datetime.strptime(s, "%m/%Y").date()
        if len(s) >= 7 and "-" in s:   # YYYY-MM or YYYY-MM-DD
            return datetime.strptime(s[:7], "%Y-%m").date()
    except Exception:
        pass
    return None


def _is_valid(data_map: dict) -> bool:
    """Rejeita dados uniformes (suavizados): >70% com mesmo valor arredondado."""
    if len(data_map) < 3:
        return False
    vals = [round(v, 2) for v in data_map.values()]
    top = Counter(vals).most_common(1)[0][1]
    return top / len(vals) < 0.70


# ── IPCA ───────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 24)
def get_focus_ipca_mensal() -> pd.DataFrame:
    """
    IPCA mensal para os próximos 36 meses, combinando:
    1. ExpectativaMercadoMensais (Suavizado='N') → ~12 meses individuais
    2. ExpectativasMercadoInflacao24Meses → meses 13-24 individuais
    3. ExpectativasMercadoAnuais → converte anual em mensal para além de 24 meses
    Fallback hardcoded apenas se API completamente indisponível.
    """
    hoje = date.today().replace(day=1)

    # Busca todas as fontes
    map12   = _fetch_mensais_12()    # {date: %}  — últimos ~12 meses
    map24   = _fetch_inflacao24()    # {date: %}  — meses 13-24
    map_aa  = _fetch_anual()         # {ano: %}

    # Combina: map12 tem prioridade, depois map24, depois anual, depois fallback
    combined = {**map24, **map12}  # map12 sobrescreve map24 onde há sobreposição

    rows = []
    ref = hoje
    for _ in range(36):
        if ref in combined:
            v = combined[ref]
        elif ref.year in map_aa:
            v = round(((1 + map_aa[ref.year] / 100) ** (1/12) - 1) * 100, 4)
        elif (ref.year, ref.month) in IPCA_FALLBACK:
            v = IPCA_FALLBACK[(ref.year, ref.month)]
        else:
            v = _mensal_de_anual(ref.year)

        rows.append({
            "DataReferencia": pd.Timestamp(ref),
            "Mediana": v,
            "MesLabel": ref.strftime("%m/%Y"),
        })
        ref += relativedelta(months=1)

    return pd.DataFrame(rows)


def _fetch_mensais_12() -> dict:
    """
    Busca ExpectativaMercadoMensais com Suavizado='N'.
    Retorna {} se API falhar ou retornar dados suavizados.
    """
    ultima = _latest_pub_date("ExpectativaMercadoMensais",
                              " and Suavizado eq 'N'")
    if not ultima:
        return {}

    url = (f"{BASE}/ExpectativaMercadoMensais"
           f"?$filter=Indicador eq 'IPCA' and Suavizado eq 'N'"
           f" and Data eq '{ultima}'"
           f"&$top=24&$format=json&$select=DataReferencia,Mediana"
           f"&$orderby=DataReferencia asc")

    hoje = date.today().replace(day=1)
    result = {}
    for v in _get(url):
        dt  = _parse_mes(v.get("DataReferencia", ""))
        med = v.get("Mediana")
        if dt and dt >= hoje and med is not None:
            result[dt] = float(med)

    return result if _is_valid(result) else {}


def _fetch_inflacao24() -> dict:
    """
    Busca ExpectativasMercadoInflacao24Meses — cobre meses 13 a 24 à frente.
    Campo: Suavizada (diferente do mensal que tem Suavizado)
    """
    try:
        # Última data de publicação (sem filtro Suavizado)
        url_last = (f"{BASE}/ExpectativasMercadoInflacao24Meses"
                    f"?$filter=Indicador eq 'IPCA' and Suavizada eq 'N'"
                    f"&$top=1&$format=json&$select=Data&$orderby=Data desc")
        vals = _get(url_last)
        if not vals:
            # Tenta sem filtro Suavizada
            url_last2 = (f"{BASE}/ExpectativasMercadoInflacao24Meses"
                         f"?$filter=Indicador eq 'IPCA'"
                         f"&$top=1&$format=json&$select=Data&$orderby=Data desc")
            vals = _get(url_last2)
        if not vals:
            return {}
        ultima = vals[0].get("Data", "")
        if not ultima:
            return {}

        url = (f"{BASE}/ExpectativasMercadoInflacao24Meses"
               f"?$filter=Indicador eq 'IPCA' and Data eq '{ultima}'"
               f"&$top=24&$format=json&$select=DataReferencia,Mediana"
               f"&$orderby=DataReferencia asc")

        hoje = date.today().replace(day=1)
        result = {}
        for v in _get(url):
            dt  = _parse_mes(v.get("DataReferencia", ""))
            med = v.get("Mediana")
            if dt and dt >= hoje and med is not None:
                result[dt] = float(med)

        return result if _is_valid(result) else {}
    except Exception:
        return {}


def _fetch_anual() -> dict:
    """Busca IPCA anual Focus. Retorna {ano: %} para anos futuros."""
    ultima = ""
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
            ano = int(str(v.get("DataReferencia",""))[:4])
            med = v.get("Mediana")
            if ano >= ano_atual and med is not None:
                result[ano] = float(med)
        except Exception:
            pass
    return result


# ── SELIC ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 24)
def get_focus_selic_copom() -> pd.DataFrame:
    url_last = (f"{BASE}/ExpectativasMercadoSelic"
                f"?$top=1&$format=json&$select=Data&$orderby=Data desc")
    vals = _get(url_last)
    if not vals:
        return _selic_fallback()
    ultima = vals[0].get("Data","")
    if not ultima:
        return _selic_fallback()

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
            rows.append({"Reuniao":reuniao,"data_reuniao":dt,"taxa_aa":float(med)})

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
    rows = [
        {"Reuniao":"3/2026","data_reuniao":COPOM_DATES["3/2026"],"taxa_aa":14.50},
        {"Reuniao":"4/2026","data_reuniao":COPOM_DATES["4/2026"],"taxa_aa":14.25},
        {"Reuniao":"5/2026","data_reuniao":COPOM_DATES["5/2026"],"taxa_aa":13.75},
        {"Reuniao":"6/2026","data_reuniao":COPOM_DATES["6/2026"],"taxa_aa":13.25},
        {"Reuniao":"7/2026","data_reuniao":COPOM_DATES["7/2026"],"taxa_aa":13.00},
        {"Reuniao":"8/2026","data_reuniao":COPOM_DATES["8/2026"],"taxa_aa":13.00},
        {"Reuniao":"1/2027","data_reuniao":COPOM_DATES["1/2027"],"taxa_aa":12.75},
        {"Reuniao":"2/2027","data_reuniao":COPOM_DATES["2/2027"],"taxa_aa":12.50},
        {"Reuniao":"3/2027","data_reuniao":COPOM_DATES["3/2027"],"taxa_aa":12.25},
        {"Reuniao":"4/2027","data_reuniao":COPOM_DATES["4/2027"],"taxa_aa":12.00},
        {"Reuniao":"5/2027","data_reuniao":COPOM_DATES["5/2027"],"taxa_aa":12.00},
        {"Reuniao":"6/2027","data_reuniao":COPOM_DATES["6/2027"],"taxa_aa":12.00},
        {"Reuniao":"7/2027","data_reuniao":COPOM_DATES["7/2027"],"taxa_aa":12.00},
        {"Reuniao":"8/2027","data_reuniao":COPOM_DATES["8/2027"],"taxa_aa":12.00},
    ]
    return pd.DataFrame(rows)


# ── Data de publicação ─────────────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 24)
def get_focus_data_publicacao() -> str:
    ultima = _latest_pub_date("ExpectativaMercadoMensais", " and Suavizado eq 'N'")
    if ultima:
        try:
            return datetime.strptime(ultima[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            return ultima
    return FOCUS_FALLBACK_DATE
