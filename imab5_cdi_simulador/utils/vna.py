"""
Cálculo do VNA (Valor Nominal Atualizado) conforme metodologia ANBIMA.

Metodologia correta (ciclos de 15 a 15):
  VNA(d) = VNA(15_mês_anterior) × (1 + IPCA_mês)^(DU_de_15ant_a_d / DU_de_15ant_a_15prox)

Onde:
  - VNA(15_mês_anterior) = VNA no dia 15 do mês anterior (ou último DU antes do 15)
  - IPCA_mês = IPCA do mês de referência (Focus ou ANBIMA)
  - DU_de_15ant_a_d = dias úteis do 15 anterior até d (exclusive 15ant, inclusive d)
  - DU_de_15ant_a_15prox = dias úteis do 15 anterior ao 15 seguinte (total do ciclo)
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Optional
import streamlit as st
from pathlib import Path

from utils.business_days import (
    load_holidays,
    is_business_day,
    count_business_days,
    business_days_range,
)


@st.cache_data
def load_vna_historico(uploaded_file=None) -> pd.DataFrame:
    """
    Carrega VNA histórico ANBIMA.
    Retorna DataFrame: Data (date), VNA (float), Ref (str), Índice (float)
    """
    try:
        if uploaded_file is not None:
            df = pd.read_excel(uploaded_file, sheet_name="NTN-B")
        else:
            path = Path(__file__).parent.parent / "data" / "VNA_ANBIMA__Dados_históricos.xlsx"
            if not path.exists():
                return pd.DataFrame(columns=["Data", "VNA", "Ref", "Índice"])
            df = pd.read_excel(path, sheet_name="NTN-B")

        df = df.rename(columns={"Data de Referência": "Data"})
        df["Data"] = pd.to_datetime(df["Data"]).dt.date
        cols = ["Data", "VNA", "Ref"]
        if "Índice" in df.columns:
            cols.append("Índice")
        df = df[cols].dropna(subset=["VNA"])
        df = df.sort_values("Data").drop_duplicates(subset="Data", keep="last")
        return df.reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["Data", "VNA", "Ref", "Índice"])


def get_vna_at_date(target_date: date, df_vna: pd.DataFrame) -> Optional[float]:
    """Retorna VNA em target_date ou o mais recente anterior."""
    if df_vna.empty:
        return None
    df = df_vna.copy()
    df["Data"] = pd.to_datetime(df["Data"]).dt.date
    sub = df[df["Data"] <= target_date]
    return float(sub.iloc[-1]["VNA"]) if not sub.empty else None


def get_vna_exact_or_nearest(target_date: date, df_vna: pd.DataFrame) -> Optional[float]:
    """Retorna VNA exato ou anterior mais próximo."""
    if df_vna.empty:
        return None
    df = df_vna.copy()
    df["Data"] = pd.to_datetime(df["Data"]).dt.date
    exact = df[df["Data"] == target_date]
    if not exact.empty:
        return float(exact.iloc[-1]["VNA"])
    before = df[df["Data"] < target_date]
    if not before.empty:
        return float(before.iloc[-1]["VNA"])
    after = df[df["Data"] > target_date]
    return float(after.iloc[0]["VNA"]) if not after.empty else None


def build_ipca_monthly_map(ipca_df: pd.DataFrame, start_date: date, end_date: date) -> dict:
    """Constrói mapa {(ano, mes): variacao%} a partir do DataFrame de IPCA."""
    mapping = {}
    for _, row in ipca_df.iterrows():
        dt = row["DataReferencia"]
        if isinstance(dt, pd.Timestamp):
            dt = dt.date()
        mapping[(dt.year, dt.month)] = float(row["Mediana"])
    return mapping


def _nearest_15th(ref_date: date, direction: str, holidays: set) -> date:
    """
    Retorna o dia 15 (ou DU mais próximo) do mês indicado.
    direction='prev' = 15 do mês de ref_date ou anterior
    direction='next' = 15 do mês seguinte
    """
    if direction == 'prev':
        # 15 do mês de ref_date
        d15 = date(ref_date.year, ref_date.month, 15)
    else:
        # 15 do mês seguinte
        if ref_date.month == 12:
            d15 = date(ref_date.year + 1, 1, 15)
        else:
            d15 = date(ref_date.year, ref_date.month + 1, 15)

    # Se o dia 15 não for DU, usa o próximo DU
    while not is_business_day(d15, holidays):
        d15 += timedelta(days=1)
    return d15


def project_vna_daily(
    start_date: date,
    end_date: date,
    vna_start: float,
    ipca_monthly: dict,
    holidays: set,
) -> pd.DataFrame:
    """
    Projeta VNA diariamente usando metodologia ANBIMA (ciclos de 15 a 15).

    VNA(d) = VNA(15_ant) × (1 + IPCA_ciclo)^(DU_15ant→d / DU_15ant→15prox)

    Âncora inicial: vna_start é o VNA na data start_date.
    A partir daí, back-calcula VNA(15_ant) e propaga.
    """
    all_days = business_days_range(start_date, end_date, holidays)
    if not all_days:
        return pd.DataFrame(columns=["Data", "VNA"])

    results = []

    # Para cada DU, determina seu ciclo (15_ant → 15_prox) e calcula VNA
    # Cacheamos os ciclos já calculados: {(15_ant, 15_prox): (vna_15ant, ipca)}
    cycle_cache = {}

    # Determina o ciclo de start_date
    start_15ant  = _nearest_15th(start_date, 'prev', holidays)
    # Se start_date < 15_ant (ou seja, é antes do 15 do mês), usa 15 do mês anterior
    if start_date < start_15ant:
        if start_date.month == 1:
            prev_month = date(start_date.year - 1, 12, 1)
        else:
            prev_month = date(start_date.year, start_date.month - 1, 1)
        start_15ant = _nearest_15th(prev_month, 'prev', holidays)

    # Back-calcula VNA(15_ant) a partir de vna_start
    def get_ipca_for_cycle(d15ant: date) -> float:
        """Retorna IPCA do ciclo que começa em d15ant (mês do d15ant)."""
        # O IPCA do ciclo é o IPCA do MÊS de d15ant
        # (o IPCA de abril atualiza o VNA de 15/abr a 15/mai)
        return ipca_monthly.get((d15ant.year, d15ant.month), 0.0) / 100.0

    def get_or_build_cycle(d: date) -> tuple:
        """
        Retorna (vna_15ant, ipca, d15ant, d15prox, du_total) para o ciclo de d.
        """
        # Determina 15_ant e 15_prox do ciclo de d
        d15ant = _nearest_15th(d, 'prev', holidays)
        if d < d15ant:
            # d está antes do 15 do mês → ciclo é 15 do mês anterior
            if d.month == 1:
                d15ant = _nearest_15th(date(d.year-1, 12, 15), 'prev', holidays)
            else:
                d15ant = _nearest_15th(date(d.year, d.month-1, 15), 'prev', holidays)

        d15prox = _nearest_15th(d15ant, 'next', holidays)
        key = (d15ant, d15prox)

        if key in cycle_cache:
            return cycle_cache[key]

        # Calcula VNA(d15ant) — apenas para o ciclo inicial, usa back-calc
        # Para ciclos subsequentes, propaga do ciclo anterior
        return key, None  # será preenchido abaixo

    # Calcula todos os ciclos necessários
    # Primeiro, identifica todos os ciclos únicos
    cycles_needed = set()
    for d in all_days:
        d15ant = _nearest_15th(d, 'prev', holidays)
        if d < d15ant:
            if d.month == 1:
                d15ant = _nearest_15th(date(d.year-1, 12, 15), 'prev', holidays)
            else:
                d15ant = _nearest_15th(date(d.year, d.month-1, 15), 'prev', holidays)
        d15prox = _nearest_15th(d15ant, 'next', holidays)
        cycles_needed.add((d15ant, d15prox))

    cycles_sorted = sorted(cycles_needed)

    # Back-calcula VNA(15_ant) do primeiro ciclo a partir de vna_start
    first_15ant, first_15prox = cycles_sorted[0]
    first_ipca = get_ipca_for_cycle(first_15ant)
    du_first_total = count_business_days(first_15ant, first_15prox, holidays)

    # DU acumulados de first_15ant até start_date
    du_acum_start = count_business_days(first_15ant, start_date, holidays)

    if first_ipca > 0 and du_first_total > 0:
        vna_15ant_first = vna_start / (1 + first_ipca) ** (du_acum_start / du_first_total)
    else:
        vna_15ant_first = vna_start

    cycle_cache[(first_15ant, first_15prox)] = {
        "vna_15ant": vna_15ant_first,
        "ipca": first_ipca,
        "du_total": du_first_total,
    }

    # Propaga VNA para ciclos subsequentes
    for i in range(1, len(cycles_sorted)):
        prev_15ant, prev_15prox = cycles_sorted[i-1]
        curr_15ant, curr_15prox = cycles_sorted[i]

        prev = cycle_cache[(prev_15ant, prev_15prox)]
        # VNA(15_prox do ciclo anterior) = VNA(15_ant_atual)
        vna_15ant_curr = prev["vna_15ant"] * (1 + prev["ipca"])

        curr_ipca = get_ipca_for_cycle(curr_15ant)
        du_curr_total = count_business_days(curr_15ant, curr_15prox, holidays)

        cycle_cache[(curr_15ant, curr_15prox)] = {
            "vna_15ant": vna_15ant_curr,
            "ipca": curr_ipca,
            "du_total": du_curr_total,
        }

    # Calcula VNA para cada DU
    for d in all_days:
        d15ant = _nearest_15th(d, 'prev', holidays)
        if d < d15ant:
            if d.month == 1:
                d15ant = _nearest_15th(date(d.year-1, 12, 15), 'prev', holidays)
            else:
                d15ant = _nearest_15th(date(d.year, d.month-1, 15), 'prev', holidays)
        d15prox = _nearest_15th(d15ant, 'next', holidays)
        key = (d15ant, d15prox)

        cycle = cycle_cache.get(key)
        if not cycle:
            results.append({"Data": d, "VNA": 0.0})
            continue

        du_acum = count_business_days(d15ant, d, holidays)
        du_total = cycle["du_total"]
        vna_15ant = cycle["vna_15ant"]
        ipca = cycle["ipca"]

        if du_total > 0:
            fator = (1 + ipca) ** (du_acum / du_total)
        else:
            fator = 1.0

        results.append({"Data": d, "VNA": round(vna_15ant * fator, 6)})

    return pd.DataFrame(results)


def calcular_retorno_imab5(
    data_inicio: date,
    data_fim: date,
    taxa_real_aa: float,
    duration_du: float,
    vna_inicio: float,
    vna_fim: float,
    variacao_taxa_pp: float,
    holidays: set,
) -> dict:
    """
    Retorno IMA-B5:
    - Carrego real: (1+taxa_real)^(DU/252) - 1
    - IPCA: vna_fim/vna_inicio - 1
    - MTM: -duration_anos × Δtaxa
    """
    all_du = business_days_range(data_inicio, data_fim, holidays)
    du = len(all_du)
    duration_anos = duration_du / 252.0

    carrego_real = (1 + taxa_real_aa / 100.0) ** (du / 252.0) - 1.0
    fator_vna = vna_fim / vna_inicio if vna_inicio > 0 else 1.0
    ipca_periodo = fator_vna - 1.0
    retorno_carrego = (1 + carrego_real) * fator_vna - 1.0
    impacto_mtm = -(duration_anos * variacao_taxa_pp / 100.0)
    retorno_total = retorno_carrego + impacto_mtm

    return {
        "du": du,
        "duration_anos": duration_anos,
        "carrego_real": carrego_real,
        "ipca_periodo": ipca_periodo,
        "fator_vna": fator_vna,
        "retorno_carrego": retorno_carrego,
        "impacto_mtm": impacto_mtm,
        "retorno_total": retorno_total,
        "variacao_taxa_pp": variacao_taxa_pp,
    }


def calcular_retorno_cdi(
    data_inicio: date,
    data_fim: date,
    selic_reunioes: list,
    holidays: set,
) -> dict:
    """
    CDI acumulado: acumula DU a partir de data_inicio (inclusive).
    CDI diário = (1 + selic_aa)^(1/252) - 1
    """
    all_days = business_days_range(data_inicio, data_fim, holidays)
    if not all_days:
        return {"retorno_cdi": 0.0, "du": 0, "taxa_media": 0.0, "indice_final": 1.0}

    reunioes = sorted(selic_reunioes, key=lambda x: x["data_reuniao"])
    taxa_inicial = reunioes[0]["taxa_aa"] if reunioes else 14.75
    for r in reunioes:
        if r["data_reuniao"] <= data_inicio:
            taxa_inicial = r["taxa_aa"]

    indice = 1.0
    soma_taxas = 0.0

    for d in all_days:
        taxa_vigente = taxa_inicial
        for r in reunioes:
            if r["data_reuniao"] <= d:
                taxa_vigente = r["taxa_aa"]
            else:
                break
        indice *= (1 + taxa_vigente / 100.0) ** (1.0 / 252.0)
        soma_taxas += taxa_vigente

    du_total = len(all_days)
    return {
        "retorno_cdi": indice - 1.0,
        "du": du_total,
        "taxa_media": soma_taxas / du_total if du_total > 0 else 0.0,
        "indice_final": indice,
    }
