# IMA-B 5 vs CDI — Simulador de Retornos

Simulador interativo para comparação de retornos esperados entre IMA-B 5 e CDI,
com integração automática ao Relatório Focus (Banco Central do Brasil).

## Funcionalidades

- **Três Cenários**: Compare IMA-B 5 vs CDI com abertura/fechamento de curva configurável
- **Mês a Mês**: Retorno mensal por carrego puro, sem marcação a mercado
- **Histórico VNA**: Visualização e projeção do VNA (NTN-B) com upload ANBIMA
- **Parâmetros**: IPCA e Selic em três cenários (Base/Focus, Otimista, Alternativo)
- **Carteira**: Simulação de retorno ponderado com heatmap de sensibilidade

## Instalação Local

```bash
# Clonar repositório
git clone https://github.com/SEU_USUARIO/imab5-cdi-simulador.git
cd imab5-cdi-simulador

# Instalar dependências
pip install -r requirements.txt

# Executar
streamlit run app.py
```

## Deploy no Streamlit Cloud

1. Faça fork ou push deste repositório para o GitHub
2. Acesse [share.streamlit.io](https://share.streamlit.io)
3. Clique em **"New app"**
4. Selecione o repositório e branch (main)
5. **Main file path**: `app.py`
6. Clique em **Deploy**

O app ficará disponível em: `https://SEU_USUARIO-imab5-cdi-simulador-app-XXXXX.streamlit.app`

## Estrutura do Projeto

```
imab5_cdi_app/
├── app.py                    # Entrada principal
├── requirements.txt          # Dependências
├── .streamlit/
│   └── config.toml           # Configuração do tema
├── pages/
│   ├── cenarios.py           # Aba: Três Cenários
│   ├── mes_a_mes.py          # Aba: Retorno Mês a Mês
│   ├── historico_vna.py      # Aba: Histórico VNA
│   ├── parametros.py         # Aba: Parâmetros
│   └── carteira.py           # Aba: Simulador de Carteira
├── utils/
│   ├── business_days.py      # Cálculo de dias úteis e feriados
│   ├── focus_api.py          # Integração API Focus/BCB
│   ├── vna.py                # Engine de cálculo VNA e retornos
│   └── session_state.py      # Gerenciamento de estado
└── data/
    ├── feriados_nacionais.xls       # Feriados nacionais
    └── VNA_ANBIMA__Dados_históricos.xlsx  # VNA histórico inicial
```

## Metodologia

### VNA (Valor Nominal Atualizado)
Conforme metodologia ANBIMA para NTN-B:
```
VNA(d) = VNA_início_mês × (1 + IPCA_mês)^(DU_acumulados / DU_total_mês)
```

### Retorno IMA-B 5
```
Retorno = Carrego_real × Fator_VNA + Impacto_MTM
Impacto_MTM = -Duration_anos × Δtaxa
Carrego_real = (1 + taxa_real)^(DU/252) - 1
```

### Retorno CDI
```
Retorno_CDI = ∏ (1 + Selic_vigente)^(1/252) - 1
```
Selic vigente atualizada a cada reunião COPOM conforme projeção Focus.

## Atualização de Dados

- **Focus**: Automático via API BCB (cache de 6h), botão "Atualizar Focus"
- **VNA**: Upload manual do arquivo ANBIMA na aba "Histórico VNA"
- **Feriados**: Arquivo `data/feriados_nacionais.xls` (já incluído até 2030+)

## Dependências

```
streamlit>=1.32.0
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.18.0
openpyxl>=3.1.0
xlrd>=2.0.1
requests>=2.31.0
python-dateutil>=2.8.2
```
