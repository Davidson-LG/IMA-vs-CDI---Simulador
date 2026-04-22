"""
Cálculo do VNA (Valor Nominal Atualizado) conforme metodologia ANBIMA.
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
    Carrega VNA histórico.
    Retorna DataFrame com colunas: Data (date), VNA (float), Ref (str)
    """
    try:
        if uploaded_file is not None:
            df = pd.read_excel(uploaded_file, sheet_name="NTN-B")
        else:
            path = Path(__file__).parent.parent / "data" / "VNA_ANBIMA__Dados_históricos.xlsx"
            if not path.exists():
                return pd.DataFrame(columns=["Data", "VNA", "Ref"])
            df = pd.read_excel(path, sheet_name="NTN-B")

        df = df.rename(columns={"Data de Referência": "Data"})
        df["Data"] = pd.to_datetime(df["Data"]).dt.date
        df = df[["Data", "VNA", "Ref"]].dropna(subset=["VNA"])
        df = df.sort_values("Data").drop_duplicates(subset="Data", keep="last")
        return df.reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["Data", "VNA", "Ref"])


def get_vna_at_date(target_date: date, df_vna: pd.DataFrame) -> Optional[float]:
    """
    Retorna o VNA em uma data específica.
    Se não existir exatamente, retorna o último disponível anterior.
    """
    if df_vna.empty:
        return None
    df = df_vna.copy()
    df["Data"] = pd.to_datetime(df["Data"]).dt.date
    subset = df[df["Data"] <= target_date]
    if subset.empty:
        return None
    return float(subset.iloc[-1]["VNA"])


def get_vna_exact_or_nearest(target_date: date, df_vna: pd.DataFrame) -> Optional[float]:
    """
    Retorna VNA exato na data, ou o mais próximo disponível.
    Útil para lookup mês a mês.
    """
    if df_vna.empty:
        return None
    df = df_vna.copy()
    df["Data"] = pd.to_datetime(df["Data"]).dt.date
    # Exato
    exact = df[df["Data"] == target_date]
    if not exact.empty:
        return float(exact.iloc[-1]["VNA"])
    # Anterior mais próximo
    before = df[df["Data"] < target_date]
    if not before.empty:
        return float(before.iloc[-1]["VNA"])
    # Posterior mais próximo
    after = df[df["Data"] > target_date]
    if not after.empty:
        return float(after.iloc[0]["VNA"])
    return None


def build_ipca_monthly_map(ipca_df: pd.DataFrame, start_date: date, end_date: date) -> dict:
    """
    Constrói mapa {(ano, mes): variacao_mensal_%} para o período.
    """
    mapping = {}
    for _, row in ipca_df.iterrows():
        dt = row["DataReferencia"]
        if isinstance(dt, pd.Timestamp):
            dt = dt.date()
        mapping[(dt.year, dt.month)] = float(row["Mediana"])
    return mapping


def project_vna_daily(
    start_date: date,
    end_date: date,
    vna_start: float,
    ipca_monthly: dict,
    holidays: set,
) -> pd.DataFrame:
    """
    Projeta VNA diariamente do start_date até end_date.

    Metodologia ANBIMA:
      VNA(d) = VNA_base_mes × (1 + ipca_mes)^(du_acum_no_mes / du_total_mes)

    VNA_base_mes é back-calculado a partir do vna_start na data inicial,
    garantindo continuidade com o VNA ANBIMA fornecido.
    """
    all_days = business_days_range(start_date, end_date, holidays)
    if not all_days:
        return pd.DataFrame(columns=["Data", "VNA"])

    months_needed = sorted(set((d.year, d.month) for d in all_days))

    # Calcula total de DU por mês
    mes_info = {}
    for yr, mo in months_needed:
        if mo == 12:
            mes_fim = date(yr + 1, 1, 1) - timedelta(days=1)
        else:
            mes_fim = date(yr, mo + 1, 1) - timedelta(days=1)
        du_total = count_business_days(date(yr, mo, 1) - timedelta(days=1), mes_fim, holidays)
        mes_info[(yr, mo)] = {"du_total": max(du_total, 1), "vna_base": None}

    # Back-calcula VNA base do primeiro mês a partir do vna_start
    first_yr, first_mo = months_needed[0]
    first_ipca = ipca_monthly.get((first_yr, first_mo), 0.0) / 100.0
    first_du_total = mes_info[(first_yr, first_mo)]["du_total"]
    du_acum_start = count_business_days(
        date(first_yr, first_mo, 1) - timedelta(days=1), start_date, holidays
    )
    if first_ipca > 0 and first_du_total > 0:
        fator_start = (1 + first_ipca) ** (du_acum_start / first_du_total)
        vna_base_first = vna_start / fator_start
    else:
        vna_base_first = vna_start

    # Propaga VNA base mês a mês
    last_vna = vna_base_first
    for yr, mo in months_needed:
        mes_info[(yr, mo)]["vna_base"] = last_vna
        ipca_rate = ipca_monthly.get((yr, mo), 0.0) / 100.0
        last_vna = last_vna * (1 + ipca_rate)

    # Calcula VNA para cada DU
    results = []
    for d in all_days:
        yr, mo = d.year, d.month
        du_acum = count_business_days(date(yr, mo, 1) - timedelta(days=1), d, holidays)
        du_total = mes_info[(yr, mo)]["du_total"]
        vna_base = mes_info[(yr, mo)]["vna_base"]
        ipca_rate = ipca_monthly.get((yr, mo), 0.0) / 100.0
        fator = (1 + ipca_rate) ** (du_acum / du_total) if du_total > 0 else 1.0
        results.append({"Data": d, "VNA": round(vna_base * fator, 6)})

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
    Calcula retorno IMA-B 5 no período.

    Componentes:
    1. IPCA acumulado: vna_fim / vna_inicio - 1  (variação do VNA)
    2. Carrego real:   (1 + taxa_real)^(du/252) - 1
    3. Retorno carrego total: (1 + carrego_real) * (vna_fim/vna_inicio) - 1
    4. MTM: -duration_anos × Δtaxa
    5. Retorno total: carrego + MTM
    """
    # DU contados de forma inclusiva (como na planilha: inclui data_inicio)
    all_du = business_days_range(data_inicio, data_fim, holidays)
    du = len(all_du)
    duration_anos = duration_du / 252.0

    carrego_real = (1 + taxa_real_aa / 100.0) ** (du / 252.0) - 1.0

    if vna_inicio > 0:
        fator_vna = vna_fim / vna_inicio
    else:
        fator_vna = 1.0
    ipca_periodo = fator_vna - 1.0

    # Retorno de carrego = componente real × componente IPCA
    retorno_carrego = (1 + carrego_real) * fator_vna - 1.0

    # Impacto MTM
    delta_taxa = variacao_taxa_pp / 100.0
    impacto_mtm = -duration_anos * delta_taxa

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
    Calcula retorno CDI acumulado no período.
    selic_reunioes: lista de dicts com 'data_reuniao' (date) e 'taxa_aa' (float %)

    CDI diário = (1 + taxa_aa/100)^(1/252) - 1
    """
    # Planilha: acumula a partir de data_inicio INCLUSIVE
    # (base = dia anterior a data_inicio, conforme CDI sheet: DU=0 = dia antes)
    all_days = business_days_range(data_inicio, data_fim, holidays)
    if not all_days:
        return {"retorno_cdi": 0.0, "du": 0, "taxa_media": 0.0, "indice_final": 1.0}

    reunioes = sorted(selic_reunioes, key=lambda x: x["data_reuniao"])

    # Taxa inicial: última reunião anterior ou igual a data_inicio
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
        fator_diario = (1 + taxa_vigente / 100.0) ** (1.0 / 252.0)
        indice *= fator_diario
        soma_taxas += taxa_vigente

    du_total = len(all_days)
    return {
        "retorno_cdi": indice - 1.0,
        "du": du_total,
        "taxa_media": soma_taxas / du_total if du_total > 0 else 0.0,
        "indice_final": indice,
    }
