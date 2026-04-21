"""
Cálculo do VNA (Valor Nominal Atualizado) conforme metodologia ANBIMA.

Referência: Metodologias ANBIMA de Precificação de Títulos Públicos
- NTN-B: VNA atualizado pelo IPCA
- VNA base em 15/07/2000 = R$ 1.000,00

Metodologia diária:
VNA(t) = VNA(t-1) × (1 + IPCA_mensal)^(du_corridos_no_mês / du_total_mês)

Para projeção:
- Usa variação mensal do IPCA projetado (Focus ou manual)
- Proporção diária pela contagem de dias úteis dentro do mês de referência
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


VNA_BASE_DATE = date(2000, 7, 15)
VNA_BASE_VALUE = 1000.0


@st.cache_data
def load_vna_historico(uploaded_file=None) -> pd.DataFrame:
    """
    Carrega VNA histórico.
    Prioridade: arquivo enviado pelo usuário > arquivo padrão do projeto.
    Retorna DataFrame com colunas: Data, VNA, Ref ('F'=fechado, 'P'=projeção)
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
        df = df.reset_index(drop=True)
        return df
    except Exception as e:
        return pd.DataFrame(columns=["Data", "VNA", "Ref"])


def get_vna_at_date(target_date: date, df_vna: pd.DataFrame) -> Optional[float]:
    """
    Retorna o VNA em uma data específica.
    Se a data não for dia útil ou não existir, retorna o último disponível.
    """
    if df_vna.empty:
        return None
    df_vna["Data"] = pd.to_datetime(df_vna["Data"]).dt.date
    subset = df_vna[df_vna["Data"] <= target_date]
    if subset.empty:
        return None
    return float(subset.iloc[-1]["VNA"])


def build_ipca_monthly_map(
    ipca_projetado: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> dict:
    """
    Constrói mapa {(ano, mes): variacao_mensal_%} para o período.
    ipca_projetado: DataFrame com colunas DataReferencia (Timestamp) e Mediana (%)
    """
    mapping = {}
    for _, row in ipca_projetado.iterrows():
        dt = row["DataReferencia"]
        if isinstance(dt, pd.Timestamp):
            dt = dt.date()
        key = (dt.year, dt.month)
        mapping[key] = float(row["Mediana"])
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
    Para cada dia útil d no mês M:
      VNA(d) = VNA_inicio_mes × (1 + ipca_M/100)^(du_acumulados_no_mes / du_total_mes)

    Onde:
    - VNA_inicio_mes = VNA do último dia útil do mês anterior
    - du_acumulados_no_mes = dias úteis desde o início do mês até d (inclusive)
    - du_total_mes = total de dias úteis no mês M

    Retorna DataFrame com colunas: Data, VNA
    """
    all_days = business_days_range(start_date, end_date, holidays)
    if not all_days:
        return pd.DataFrame(columns=["Data", "VNA"])

    results = []
    current_vna = vna_start

    # Agrupar por mês
    months_needed = sorted(set((d.year, d.month) for d in all_days))

    # VNA de início de cada mês (último dia útil do mês anterior)
    vna_inicio_mes = {}

    # Calcular total de DU por mês
    for yr, mo in months_needed:
        # Início e fim do mês
        mes_inicio = date(yr, mo, 1)
        if mo == 12:
            mes_fim = date(yr + 1, 1, 1) - timedelta(days=1)
        else:
            mes_fim = date(yr, mo + 1, 1) - timedelta(days=1)

        du_mes = count_business_days(
            date(yr, mo, 1) - timedelta(days=1), mes_fim, holidays
        )
        vna_inicio_mes[(yr, mo)] = {"du_total": du_mes, "vna_base": None}

    # Propagar VNA base mês a mês
    # Para o primeiro mês: vna_start já tem o IPCA acumulado até start_date.
    # O VNA_base_do_mês é back-calculado para então projetar uniformemente.
    first_yr, first_mo = months_needed[0]
    first_ipca = ipca_monthly.get((first_yr, first_mo), 0.0) / 100.0
    first_du_total = vna_inicio_mes[(first_yr, first_mo)]["du_total"]

    # DU acumulados desde o 1º do mês até start_date (inclusive)
    du_acum_start = count_business_days(
        date(first_yr, first_mo, 1) - timedelta(days=1), start_date, holidays
    )

    # VNA_base_do_mês = vna_start / (1 + ipca)^(du_acum_start/du_total)
    # (back-calcula o VNA de início do mês a partir do VNA ANBIMA no start_date)
    if first_du_total > 0 and first_ipca > 0:
        fator_start = (1 + first_ipca) ** (du_acum_start / first_du_total)
        vna_base_primeiro_mes = vna_start / fator_start
    else:
        vna_base_primeiro_mes = vna_start

    last_vna = vna_base_primeiro_mes
    for yr, mo in months_needed:
        vna_inicio_mes[(yr, mo)]["vna_base"] = last_vna
        ipca_rate = ipca_monthly.get((yr, mo), 0.0) / 100.0
        # VNA ao final do mês
        last_vna = last_vna * (1 + ipca_rate)

    # Calcular VNA para cada dia útil
    for d in all_days:
        yr, mo = d.year, d.month

        # du acumulados dentro do mês até d (desde o 1º do mês)
        du_acum = count_business_days(
            date(yr, mo, 1) - timedelta(days=1), d, holidays
        )
        du_total = vna_inicio_mes[(yr, mo)]["du_total"]
        vna_base = vna_inicio_mes[(yr, mo)]["vna_base"]
        ipca_rate = ipca_monthly.get((yr, mo), 0.0) / 100.0

        if du_total > 0:
            fator = (1 + ipca_rate) ** (du_acum / du_total)
        else:
            fator = 1.0

        vna_dia = vna_base * fator
        results.append({"Data": d, "VNA": round(vna_dia, 6)})

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
    Calcula o retorno esperado do IMA-B 5 no período.

    Componentes:
    1. Carrego real: (1 + taxa_real)^(du/252) - 1
    2. IPCA acumulado: VNA_fim/VNA_inicio - 1
    3. Marcação a mercado: -duration_anos × Δtaxa (em decimal)

    Retorna dict com todos os componentes.
    """
    du = count_business_days(data_inicio, data_fim, holidays)
    duration_anos = duration_du / 252.0

    # Retorno de carrego (componente real)
    carrego_real = (1 + taxa_real_aa / 100.0) ** (du / 252.0) - 1.0

    # Variação VNA (componente inflação)
    if vna_inicio > 0:
        fator_vna = vna_fim / vna_inicio
    else:
        fator_vna = 1.0
    ipca_periodo = fator_vna - 1.0

    # Retorno total de carrego (real + IPCA)
    retorno_carrego = (1 + carrego_real) * fator_vna - 1.0

    # Impacto marcação a mercado: -duration × Δtaxa
    delta_taxa = variacao_taxa_pp / 100.0  # converte pp para decimal
    impacto_mtm = -duration_anos * delta_taxa

    # Retorno total
    retorno_total = retorno_carrego + impacto_mtm

    return {
        "du": du,
        "duration_anos": duration_anos,
        "carrego_real": carrego_real,
        "ipca_periodo": ipca_periodo,
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

    selic_reunioes: lista de dicts com chaves 'data_reuniao' (date) e 'taxa_aa' (float %)
    Ordena por data e aplica cada taxa nos DU entre reuniões.

    CDI diário = (1 + taxa_aa)^(1/252) - 1
    """
    du_total = count_business_days(data_inicio, data_fim, holidays)
    all_days = business_days_range(
        data_inicio + timedelta(days=1), data_fim, holidays
    )

    if not all_days:
        return {"retorno_cdi": 0.0, "du": 0, "taxa_media": 0.0}

    # Montar calendário de taxas
    reunioes = sorted(selic_reunioes, key=lambda x: x["data_reuniao"])

    indice = 1.0
    taxa_media_pond = 0.0

    for d in all_days:
        # Taxa vigente = última reunião anterior ou igual a d
        taxa_vigente = reunioes[0]["taxa_aa"] if reunioes else 12.25
        for r in reunioes:
            if r["data_reuniao"] <= d:
                taxa_vigente = r["taxa_aa"]
            else:
                break

        fator_diario = (1 + taxa_vigente / 100.0) ** (1 / 252.0)
        indice *= fator_diario
        taxa_media_pond += taxa_vigente

    retorno_cdi = indice - 1.0
    taxa_media = taxa_media_pond / len(all_days) if all_days else 0.0

    return {
        "retorno_cdi": retorno_cdi,
        "du": du_total,
        "taxa_media": taxa_media,
        "indice_final": indice,
    }


def calcular_retorno_mensal(
    datas_mes: list,
    taxa_real_aa: float,
    duration_du: float,
    selic_reunioes: list,
    ipca_monthly: dict,
    vna_historico: pd.DataFrame,
    vna_projetado: pd.DataFrame,
    holidays: set,
) -> pd.DataFrame:
    """
    Calcula retornos mensais (mês a mês) para IMA-B5 e CDI, sem abertura/fechamento.
    datas_mes: lista de tuplas (data_inicio, data_fim) para cada mês.
    """
    rows = []
    for inicio, fim in datas_mes:
        du = count_business_days(inicio, fim, holidays)

        # VNA
        vna_ini = _get_vna_combined(inicio, vna_historico, vna_projetado)
        vna_fim_val = _get_vna_combined(fim, vna_historico, vna_projetado)

        res_imab = calcular_retorno_imab5(
            inicio, fim, taxa_real_aa, duration_du,
            vna_ini or 1.0, vna_fim_val or 1.0, 0.0, holidays
        )
        res_cdi = calcular_retorno_cdi(inicio, fim, selic_reunioes, holidays)

        rows.append({
            "Período": f"{inicio.strftime('%b/%Y')}",
            "Início": inicio,
            "Fim": fim,
            "DU": du,
            "IPCA (%)": round(res_imab["ipca_periodo"] * 100, 4),
            "Carrego IMA-B5 (%)": round(res_imab["retorno_carrego"] * 100, 4),
            "Retorno IMA-B5 (%)": round(res_imab["retorno_total"] * 100, 4),
            "Retorno CDI (%)": round(res_cdi["retorno_cdi"] * 100, 4),
            "Diferença (IMA-CDI) pp": round(
                (res_imab["retorno_total"] - res_cdi["retorno_cdi"]) * 100, 4
            ),
        })
    return pd.DataFrame(rows)


def _get_vna_combined(
    target: date,
    df_hist: pd.DataFrame,
    df_proj: pd.DataFrame,
) -> Optional[float]:
    """Busca VNA: prioriza histórico (F), depois projetado."""
    # Histórico
    if not df_hist.empty:
        df_hist = df_hist.copy()
        df_hist["Data"] = pd.to_datetime(df_hist["Data"]).dt.date
        sub = df_hist[df_hist["Data"] <= target]
        if not sub.empty and sub.iloc[-1]["Data"] == target:
            return float(sub.iloc[-1]["VNA"])

    # Projetado
    if not df_proj.empty:
        df_proj = df_proj.copy()
        df_proj["Data"] = pd.to_datetime(df_proj["Data"]).dt.date
        sub = df_proj[df_proj["Data"] <= target]
        if not sub.empty:
            return float(sub.iloc[-1]["VNA"])

    return None
