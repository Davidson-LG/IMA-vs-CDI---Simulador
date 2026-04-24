"""
Persistência de configurações entre sessões.

Estratégia:
  - Config (taxas, datas, cenários): st.cache_resource (memória do servidor)
    Persiste enquanto o servidor Streamlit Cloud estiver ativo.
  - VNA histórico: arquivo em data/ (filesystem do servidor)
    Persiste entre sessões no mesmo deploy.

Totalmente isolado — não interfere em nenhum outro cálculo.
"""
import json
import streamlit as st
import pandas as pd
from datetime import date
from pathlib import Path

# Caminho do arquivo de config e VNA
_DATA_DIR   = Path(__file__).parent.parent / "data"
_CONFIG_FILE = _DATA_DIR / "user_config.json"
_VNA_FILE    = _DATA_DIR / "VNA_ANBIMA__Dados_históricos.xlsx"

KEYS_TO_SAVE = [
    "data_inicio", "data_fim",
    "taxa_real_aa", "duration_du",
    "cenario_ativo_selic", "cenario_ativo_ipca",
    "selic_base", "selic_otimista", "selic_alternativo",
    "ipca_otimista", "ipca_alternativo",
]


def _serialize(val):
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, pd.DataFrame):
        return None
    if isinstance(val, list):
        result = []
        for item in val:
            if isinstance(item, dict):
                new = {}
                for k, v in item.items():
                    new[k] = v.isoformat() if isinstance(v, date) else (
                             v.isoformat() if hasattr(v, 'isoformat') else v)
                result.append(new)
            else:
                result.append(item)
        return result
    return val


def _deserialize_selic(items):
    result = []
    for item in (items or []):
        if isinstance(item, dict):
            new = dict(item)
            if isinstance(new.get("data_reuniao"), str):
                try:
                    new["data_reuniao"] = date.fromisoformat(new["data_reuniao"])
                except Exception:
                    pass
            result.append(new)
    return result


def save_config():
    """Salva configurações atuais em JSON no filesystem."""
    try:
        config = {}
        for key in KEYS_TO_SAVE:
            val = st.session_state.get(key)
            if val is not None:
                config[key] = _serialize(val)
        _CONFIG_FILE.write_text(json.dumps(config, default=str), encoding="utf-8")
    except Exception:
        pass


def load_config():
    """Restaura configurações do JSON. Só executa uma vez por sessão."""
    if st.session_state.get("_config_loaded"):
        return
    st.session_state["_config_loaded"] = True

    if not _CONFIG_FILE.exists():
        return
    try:
        config = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            return

        for key, val in config.items():
            if key in st.session_state:
                continue  # não sobrescreve valor já definido

            if key in ("data_inicio", "data_fim") and isinstance(val, str):
                try:
                    val = date.fromisoformat(val)
                except Exception:
                    continue
            elif key == "taxa_real_aa" and val is not None:
                val = float(val)
            elif key == "duration_du" and val is not None:
                val = int(val)
            elif key in ("selic_base", "selic_otimista", "selic_alternativo"):
                val = _deserialize_selic(val)

            st.session_state[key] = val
    except Exception:
        pass


def save_vna(df_vna: pd.DataFrame):
    """
    Salva o DataFrame VNA como Excel em data/.
    Chamado após upload do usuário — substitui o arquivo padrão do repositório.
    """
    if df_vna is None or df_vna.empty:
        return
    try:
        df_vna.to_excel(_VNA_FILE, sheet_name="NTN-B", index=False)
    except Exception:
        pass


def load_vna() -> pd.DataFrame | None:
    """
    Carrega VNA do arquivo em data/.
    Retorna None se o arquivo não existir.
    """
    if not _VNA_FILE.exists():
        return None
    try:
        df = pd.read_excel(_VNA_FILE, sheet_name="NTN-B")
        if "Data de Referência" in df.columns:
            df = df.rename(columns={"Data de Referência": "Data"})
        df["Data"] = pd.to_datetime(df["Data"]).dt.date
        return df.sort_values("Data").drop_duplicates("Data", keep="last").reset_index(drop=True)
    except Exception:
        return None
