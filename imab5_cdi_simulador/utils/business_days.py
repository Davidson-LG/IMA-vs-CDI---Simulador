"""
Utilitários para cálculo de dias úteis considerando feriados nacionais.
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta
from pathlib import Path
import streamlit as st


@st.cache_data
def load_holidays() -> set:
    """Carrega feriados nacionais do arquivo XLS."""
    try:
        feriados_path = Path(__file__).parent.parent / "data" / "feriados_nacionais.xls"
        if not feriados_path.exists():
            # fallback: feriados fixos básicos se arquivo não encontrado
            return _feriados_fixos()
        df = pd.read_excel(feriados_path, header=None)
        datas = pd.to_datetime(df.iloc[1:, 0], errors='coerce').dropna()
        return set(datas.dt.date)
    except Exception:
        return _feriados_fixos()


def _feriados_fixos() -> set:
    """Conjunto mínimo de feriados nacionais fixos (2024-2028)."""
    feriados = set()
    for ano in range(2023, 2030):
        feriados.update([
            date(ano, 1, 1),
            date(ano, 4, 21),
            date(ano, 5, 1),
            date(ano, 9, 7),
            date(ano, 10, 12),
            date(ano, 11, 2),
            date(ano, 11, 15),
            date(ano, 11, 20),
            date(ano, 12, 25),
        ])
    return feriados


def is_business_day(d: date, holidays: set) -> bool:
    """Verifica se uma data é dia útil (não é fim de semana nem feriado)."""
    if isinstance(d, pd.Timestamp):
        d = d.date()
    return d.weekday() < 5 and d not in holidays


def count_business_days(start: date, end: date, holidays: set) -> int:
    """
    Conta dias úteis entre start (exclusive) e end (inclusive).
    Convenção ANBIMA/B3: conta a partir do dia seguinte ao start até end.
    """
    if isinstance(start, pd.Timestamp):
        start = start.date()
    if isinstance(end, pd.Timestamp):
        end = end.date()

    if end <= start:
        return 0

    count = 0
    current = start + timedelta(days=1)
    while current <= end:
        if is_business_day(current, holidays):
            count += 1
        current += timedelta(days=1)
    return count


def business_days_range(start: date, end: date, holidays: set) -> list:
    """Retorna lista de dias úteis entre start e end (ambos inclusivos se úteis)."""
    if isinstance(start, pd.Timestamp):
        start = start.date()
    if isinstance(end, pd.Timestamp):
        end = end.date()

    days = []
    current = start
    while current <= end:
        if is_business_day(current, holidays):
            days.append(current)
        current += timedelta(days=1)
    return days


def next_business_day(d: date, holidays: set) -> date:
    """Retorna o próximo dia útil a partir de d (inclusive d se for útil)."""
    if isinstance(d, pd.Timestamp):
        d = d.date()
    while not is_business_day(d, holidays):
        d += timedelta(days=1)
    return d


def get_month_end_business_days(start: date, end: date, holidays: set) -> list:
    """
    Retorna lista de datas que são o último dia útil de cada mês
    no intervalo [start, end].
    """
    results = []
    current = date(start.year, start.month, 1)
    while current <= end:
        # último dia do mês
        if current.month == 12:
            last = date(current.year + 1, 1, 1) - timedelta(days=1)
        else:
            last = date(current.year, current.month + 1, 1) - timedelta(days=1)
        # recua até achar dia útil
        while not is_business_day(last, holidays):
            last -= timedelta(days=1)
        if start <= last <= end:
            results.append(last)
        # avança para próximo mês
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return results
