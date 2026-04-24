"""
Persistência de configurações no localStorage do browser.
Salva e restaura automaticamente os parâmetros do usuário.
Totalmente isolado — não interfere em nenhum outro cálculo.
"""
import json
import streamlit as st
import pandas as pd
from datetime import date

try:
    from streamlit_local_storage import LocalStorage
    _local_storage = LocalStorage()
    _AVAILABLE = True
except Exception:
    _AVAILABLE = False

STORAGE_KEY = "imab5_config_v1"


def _serialize(val):
    """Converte valores para JSON-serializável."""
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, pd.DataFrame):
        return None  # não persiste DataFrames (VNA histórico)
    if isinstance(val, list):
        result = []
        for item in val:
            if isinstance(item, dict):
                serialized = {}
                for k, v in item.items():
                    if isinstance(v, date):
                        serialized[k] = v.isoformat()
                    elif hasattr(v, 'isoformat'):
                        serialized[k] = v.isoformat()
                    else:
                        serialized[k] = v
                result.append(serialized)
            else:
                result.append(item)
        return result
    return val


def _deserialize_selic(items: list) -> list:
    """Restaura lista selic com datas convertidas de string para date."""
    result = []
    for item in items:
        if isinstance(item, dict):
            new_item = dict(item)
            if "data_reuniao" in new_item and isinstance(new_item["data_reuniao"], str):
                try:
                    new_item["data_reuniao"] = date.fromisoformat(new_item["data_reuniao"])
                except Exception:
                    pass
            result.append(new_item)
    return result


# Chaves a salvar/restaurar (todas as configurações editáveis pelo usuário)
KEYS_TO_SAVE = [
    "data_inicio",
    "data_fim",
    "taxa_real_aa",
    "duration_du",
    "cenario_ativo_selic",
    "cenario_ativo_ipca",
    "selic_base",
    "selic_otimista",
    "selic_alternativo",
    "ipca_otimista",
    "ipca_alternativo",
    "variacao_c1",
    "variacao_c3",
]


def save_config():
    """
    Salva configurações atuais no localStorage do browser.
    Chamado automaticamente quando qualquer parâmetro muda.
    """
    if not _AVAILABLE:
        return
    try:
        config = {}
        for key in KEYS_TO_SAVE:
            val = st.session_state.get(key)
            if val is not None:
                config[key] = _serialize(val)

        _local_storage.setItem(STORAGE_KEY, json.dumps(config))
    except Exception:
        pass  # silencioso — não interrompe o app


def load_config():
    """
    Restaura configurações do localStorage no session_state.
    Chamado UMA VEZ na inicialização, antes de init_session_state.
    Só restaura chaves que ainda não foram inicializadas.
    """
    if not _AVAILABLE:
        return
    if st.session_state.get("_config_loaded"):
        return

    try:
        raw = _local_storage.getItem(STORAGE_KEY)
        if not raw:
            st.session_state["_config_loaded"] = True
            return

        config = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(config, dict):
            st.session_state["_config_loaded"] = True
            return

        for key, val in config.items():
            if key in st.session_state:
                continue  # não sobrescreve valor já definido nesta sessão

            # Reconverte tipos especiais
            if key in ("data_inicio", "data_fim") and isinstance(val, str):
                try:
                    val = date.fromisoformat(val)
                except Exception:
                    continue
            elif key in ("taxa_real_aa",) and val is not None:
                val = float(val)
            elif key in ("duration_du",) and val is not None:
                val = int(val)
            elif key in ("selic_base", "selic_otimista", "selic_alternativo") and isinstance(val, list):
                val = _deserialize_selic(val)
            elif key in ("ipca_otimista", "ipca_alternativo") and isinstance(val, list):
                pass  # já é lista de dicts serializáveis

            st.session_state[key] = val

    except Exception:
        pass
    finally:
        st.session_state["_config_loaded"] = True
