import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import re

st.set_page_config(page_title="Operação de Crédito", layout="centered")

def interpolar_flat_forward(du_alvo, curva):
    dias = sorted(curva.keys())
    if du_alvo <= dias[0]: return curva[dias[0]] / 100
    if du_alvo >= dias[-1]: return curva[dias[-1]] / 100
    
    du_ant = max([d for d in dias if d <= du_alvo])
    du_post = min([d for d in dias if d > du_alvo])
    i_ant = curva[du_ant] / 100
    i_post = curva[du_post] / 100
    
    termo_ant = (1 + i_ant) ** (du_ant / 252)
    fator_fwd = ((1 + i_post) ** (du_post / 252)) / ((1 + i_ant) ** (du_ant / 252))
    expoente_fwd = (du_alvo - du_ant) / (du_post - du_ant)
    
    taxa_interpolada = (termo_ant * (fator_fwd ** expoente_fwd)) ** (252 / du_alvo) - 1
    return taxa_interpolada

def formatar_moeda_abrev(valor):
    if abs(valor) >= 1_000_000:
        return f"{valor/1_000_000:,.2f}M".replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        return f"{valor/1_000:,.0f}k".replace(",", ".")

def parse_curva_cdi_colada(texto):
    texto_limpo = texto.replace(".", "").replace(" ", "").replace("\n", "").replace("\t", "")
    encontrados = re.findall(r'(\d+)(\d{2},\d{4})', texto_limpo)
    if not encontrados:
        return None
    try:
        resultado = {int(du): float(taxa.replace(",", ".")) for du, taxa in encontrados}
        return resultado
    except:
        return None

def validar_intervalos_ano(ano, intervalos):
    erros = []
    datas_parsed = []

    for i, iv in enumerate(intervalos):
        try:
            ini = datetime.strptime(iv['inicio'], "%m/%Y")
            fim = datetime.strptime(iv['fim'], "%m/%Y")
        except:
            erros.append(f"Intervalo {i+1}: data inválida.")
            datas_parsed.append(None)
            continue

        if ini.year != ano:
            erros.append(f"Intervalo {i+1}: início ({iv['inicio']}) deve ser do ano {ano}.")
        if fim.year != ano:
            erros.append(f"Intervalo {i+1}: fim ({iv['fim']}) deve ser do ano {ano}.")

        if ini > fim:
            erros.append(f"Intervalo {i+1}: início não pode ser posterior ao fim.")

        datas_parsed.append((ini, fim))

    validos = [(i, d) for i, d in enumerate(datas_parsed) if d is not None]
    for idx_a in range(len(validos)):
        for idx_b in range(idx_a + 1, len(validos)):
            i_a, (ini_a, fim_a) = validos[idx_a]
            i_b, (ini_b, fim_b) = validos[idx_b]
            if ini_a <= fim_b and ini_b <= fim_a:
                erros.append(f"Intervalos {i_a+1} e {i_b+1} se sobrepõem.")

    return erros

def colorir_fluxo(val):
    cor = "#2ecc71" if val >= 0 else "#e74c3c"
    return f"color: {cor}; font-weight: bold;"

st.title("⚡ Operações de Crédito")
st.markdown("Cálculo de fluxo descontado com base na curva de juros colada.")
st.markdown("Site da Curva de Juros: https://www.anbima.com.br/pt_br/informar/curvas-de-juros-fechamento.htm")

with st.expander("📈 1. Cole a Curva CDI (ANBIMA)", expanded=True):
    st.caption("Cole o bloco de texto da curva abaixo:")
    curva_raw = st.text_area("Dados da Curva",
                             value="2114,547950413,02414214,449675613,22196314,31861.00813,468712613,88061.26013,678025213,26332.52014,0008",
                             help="O sistema separa automaticamente os Dias Úteis das Taxas.")

    curva_anbima = parse_curva_cdi_colada(curva_raw)

    if curva_anbima:
        st.success(f"✅ Curva identificada: {len(curva_anbima)} vértices.")
        df_curva = pd.DataFrame(list(curva_anbima.items()), columns=['Dias Úteis', 'Taxa (%)']).sort_values('Dias Úteis')
        st.dataframe(df_curva.T, use_container_width=True)
    else:
        st.error("❌ Erro ao ler a curva. Certifique-se que os números contêm vírgulas para as taxas.")
        st.stop()

with st.expander("📅 2. Período e Configuração", expanded=True):
    col_a, col_b = st.columns(2)
    with col_a:
        inicio_default = datetime.now().strftime("%m/%Y")
        inicio_str = st.text_input("Início da Operação (mm/aaaa)", value=inicio_default)
    with col_b:
        fim_str = st.text_input("Fim da Operação (mm/aaaa)", value="12/2027")

    spread = st.number_input("Spread CDI (ex: 0.06)", value=0.06, format="%.4f", help="Taxa adicional ao CDI.")
    pagamento_str = st.text_input("Mês do Pagamento Antecipado (mm/aaaa)", value=inicio_default, help="Mês em que a Genial realizará o pagamento único ao cliente.")
    contrato_genial = st.toggle("Contrato Genial", value=False, help="Ativo = contrato Genial | Inativo = contrato externo")

    # ── Modo de Operação ──
    MODOS = {
        "📋 Modo Padrão": "padrao",
        "⚡ Modo A — Pagar desde o início, receber no pagamento": "modo_a",
        "🚀 Modo B — Receber crédito antecipado, pagar aditivo depois": "modo_b",
    }
    MODO_DESCRICOES = {
        "padrao": """
**Como funciona:**
O cliente continua pagando somente seu contrato original até o mês do pagamento. No mês configurado, a Genial faz um pagamento único equivalente ao valor presente de todos os fluxos de mercado futuros. A partir desse mês, o cliente passa a pagar também o novo contrato de mercado mensalmente.

**Exemplo — Contrato mar/25 a dez/27, pagamento em jun/25:**
- **Mar–Mai/25:** Cliente paga apenas o contrato original (ex: R$ 130/MWh)
- **Jun/25:** Genial paga o VP total ao cliente em parcela única
- **Jun/25–Dez/27:** Cliente paga contrato original + mercado mensalmente
""",
        "modo_a": """
**Como funciona:**
O cliente passa a pagar o novo contrato de mercado desde o primeiro mês da operação, antes mesmo de receber qualquer pagamento. Em contrapartida, a Genial desconta o VP de todo o período — incluindo os meses já aditivados — e entrega o crédito único no mês de pagamento configurado.

**Exemplo — Contrato mar/25 a dez/27, pagamento em jun/25:**
- **Mar–Mai/25:** Cliente paga contrato original + mercado (ex: R$ 130 + R$ 150/MWh)
- **Jun/25:** Genial paga o VP de todo o período (mar/25 → dez/27) em parcela única
- **Jun/25–Dez/27:** Cliente paga contrato original + mercado mensalmente

> O VP recebido em jun/25 é maior que no Modo Padrão, pois inclui o desconto dos meses já aditivados.
""",
        "modo_b": """
**Como funciona:**
A Genial paga o crédito ao cliente logo no primeiro mês, referente ao período do mês de pagamento até o fim do contrato. Durante o intervalo entre o início e o mês de pagamento, o cliente não paga o aditivo de mercado — apenas o contrato original. A partir do mês de pagamento, passa a pagar normalmente o novo contrato de mercado.

**Exemplo — Contrato mar/25 a dez/27, pagamento em jun/25:**
- **Mar/25:** Genial paga ao cliente o VP de jun/25 → dez/27 antecipado
- **Mar–Mai/25:** Cliente paga apenas o contrato original (ex: R$ 130/MWh), sem aditivo
- **Jun/25–Dez/27:** Cliente paga contrato original + mercado mensalmente

> O VP recebido em mar/25 é menor que nos outros modos, pois cobre apenas o período jun/25 → dez/27.
""",
    }

    modo_label = st.selectbox("Selecione o modo de operação:", options=list(MODOS.keys()))
    modo_operacao = MODOS[modo_label]
    st.info(MODO_DESCRICOES[modo_operacao])

try:
    data_inicio = datetime.strptime(inicio_str, "%m/%Y")
    data_fim = datetime.strptime(fim_str, "%m/%Y")
    data_pagamento = datetime.strptime(pagamento_str, "%m/%Y")
    hoje = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if data_inicio < hoje:
        st.error(f"Início inválido. O mês mínimo é {hoje.strftime('%m/%Y')}.")
        st.stop()
    if data_fim < data_inicio:
        st.error("A data de fim deve ser posterior ao início.")
        st.stop()
    if data_pagamento < hoje:
        st.error(f"Mês de pagamento inválido. O mês mínimo é {hoje.strftime('%m/%Y')}.")
        st.stop()
    if data_pagamento > data_fim:
        st.error("O mês de pagamento não pode ser posterior ao fim da operação.")
        st.stop()
    if modo_operacao == "modo_b" and data_pagamento <= data_inicio:
        st.error("No Modo B, o mês de pagamento deve ser posterior ao início da operação (pois há um período sem aditivo).")
        st.stop()
except ValueError:
    st.warning("Formato de data inválido.")
    st.stop()

with st.expander("💰 3. Preços e Volumes por Ano", expanded=True):
    anos = list(range(data_inicio.year, data_fim.year + 1))

    if 'intervalos' not in st.session_state:
        st.session_state.intervalos = {}
    for ano in anos:
        if ano not in st.session_state.intervalos:
            inicio_intervalo = inicio_str if ano == data_inicio.year else f"01/{ano}"
            st.session_state.intervalos[ano] = [{
                "inicio": inicio_intervalo,
                "fim": f"12/{ano}",
                "mercado": 150.0,
                "contrato": 130.0,
                "volume": 10.0
            }]

    for ano in list(st.session_state.intervalos.keys()):
        if ano not in anos:
            del st.session_state.intervalos[ano]

    dados_operacao_intervalos = {}
    for ano in anos:
        st.write(f"**Ano {ano}**")
        intervalos_ano = st.session_state.intervalos[ano]

        for i, intervalo in enumerate(intervalos_ano):
            cols1 = st.columns([2, 2, 0.5])
            with cols1[0]:
                intervalo['inicio'] = st.text_input("Início", value=intervalo['inicio'], key=f"ini_{ano}_{i}", placeholder="mm/aaaa")
            with cols1[1]:
                intervalo['fim'] = st.text_input("Fim", value=intervalo['fim'], key=f"fim_{ano}_{i}", placeholder="mm/aaaa")
            with cols1[2]:
                st.write("")
                st.write("")
                if len(intervalos_ano) > 1:
                    if st.button("🗑️", key=f"del_{ano}_{i}"):
                        st.session_state.intervalos[ano].pop(i)
                        st.rerun()

            cols2 = st.columns(3)
            with cols2[0]:
                intervalo['mercado'] = st.number_input("Mercado (R$/MWh)", value=intervalo['mercado'], key=f"m_{ano}_{i}")
            with cols2[1]:
                intervalo['contrato'] = st.number_input("Contrato (R$/MWh)", value=intervalo['contrato'], key=f"c_{ano}_{i}")
            with cols2[2]:
                intervalo['volume'] = st.number_input("Volume (MWm)", value=intervalo.get('volume', 10.0), step=0.1, key=f"v_{ano}_{i}")

            if i < len(intervalos_ano) - 1:
                st.markdown("---")

        erros_ano = validar_intervalos_ano(ano, intervalos_ano)
        for erro in erros_ano:
            st.error(f"❌ Ano {ano} — {erro}")

        if st.button(f"➕ Adicionar intervalo em {ano}", key=f"add_{ano}"):
            inicio_novo = inicio_str if ano == data_inicio.year else f"01/{ano}"
            st.session_state.intervalos[ano].append({
                "inicio": inicio_novo,
                "fim": f"12/{ano}",
                "mercado": 150.0,
                "contrato": 130.0,
                "volume": 10.0
            })
            st.rerun()

        dados_operacao_intervalos[ano] = intervalos_ano
        st.divider()

st.divider()

if st.button("🚀 Gerar Análise", use_container_width=True):

    erros_intervalo = []
    for ano, intervalos in st.session_state.intervalos.items():
        for i, intervalo in enumerate(intervalos):
            try:
                ini = datetime.strptime(intervalo['inicio'], "%m/%Y")
                if ini < hoje:
                    erros_intervalo.append(f"Ano {ano}, intervalo {i+1}: início {intervalo['inicio']} é anterior ao mês atual ({hoje.strftime('%m/%Y')})")
            except:
                erros_intervalo.append(f"Ano {ano}, intervalo {i+1}: data de início inválida ({intervalo['inicio']})")

        erros_intervalo += [f"Ano {ano} — {e}" for e in validar_intervalos_ano(ano, intervalos)]

    if erros_intervalo:
        for erro in erros_intervalo:
            st.error(f"❌ {erro}")
        st.stop()

    datas = pd.date_range(start=data_inicio, end=data_fim, freq='MS')
    df = pd.DataFrame({'Data_Obj': datas})
    df['mês'] = df['Data_Obj'].dt.strftime('%m/%Y')
    df['Ano'] = df['Data_Obj'].dt.year
    df['indices'] = range(1, len(df) + 1)
    df['Horas'] = df['Data_Obj'].dt.days_in_month * 24

    def get_campo_por_mes(data_obj, campo):
        ano = data_obj.year
        for intervalo in st.session_state.intervalos.get(ano, []):
            try:
                ini = datetime.strptime(intervalo['inicio'], "%m/%Y")
                fim = datetime.strptime(intervalo['fim'], "%m/%Y")
                if ini <= data_obj <= fim:
                    return intervalo[campo]
            except:
                pass
        intervalos_ano = st.session_state.intervalos.get(ano, [])
        return intervalos_ano[0][campo] if intervalos_ano else 0.0

    df['Preço Mercado']  = df['Data_Obj'].apply(lambda d: get_campo_por_mes(d, 'mercado'))
    df['Preço Contrato'] = df['Data_Obj'].apply(lambda d: get_campo_por_mes(d, 'contrato'))
    df['Volume']         = df['Data_Obj'].apply(lambda d: get_campo_por_mes(d, 'volume'))

    dados_operacao = {ano: {"contrato": st.session_state.intervalos[ano][0]['contrato']} for ano in anos}

    df['DU_Acumulado'] = df['indices'] * 21
    df['CDI_Anual_Interp'] = df['DU_Acumulado'].apply(lambda x: interpolar_flat_forward(x, curva_anbima))
    df['Taxa_Desconto_Mensal'] = ((1 + df['CDI_Anual_Interp']) * (1 + spread))**(1/12) - 1
    df['Fator_Desconto'] = ((1 + df['CDI_Anual_Interp']) * (1 + spread)) ** (df['DU_Acumulado'] / 252)

    # ── Índice e fator do mês de pagamento ──
    indice_pagamento = (data_pagamento.year - data_inicio.year) * 12 + (data_pagamento.month - data_inicio.month) + 1
    du_pagamento = indice_pagamento * 21
    cdi_pagamento = interpolar_flat_forward(du_pagamento, curva_anbima)
    fator_pagamento = ((1 + cdi_pagamento) * (1 + spread)) ** (du_pagamento / 252)

    # Fator de desconto relativo ao mês de pagamento
    df['Fator_Desconto_Relativo'] = df['Fator_Desconto'] / fator_pagamento

    df['Fluxo Mercado']  = df['Volume'] * df['Horas'] * df['Preço Mercado']
    df['Fluxo Contrato'] = df['Volume'] * df['Horas'] * df['Preço Contrato']

    # Índice do mês de pagamento no dataframe
    idx_pagamento = df[df['Data_Obj'] == data_pagamento].index
    idx_pag = idx_pagamento[0] if len(idx_pagamento) > 0 else df.index[0]

    if modo_operacao == "padrao":

        # VP total descontado ao mês de pagamento
        df['Cliente_Recebe_VP'] = df.apply(
            lambda row: row['Fluxo Mercado'] / row['Fator_Desconto_Relativo'] if row['Data_Obj'] >= data_pagamento else 0.0,
            axis=1
        )
        pagamento_unico = df['Cliente_Recebe_VP'].sum()

        df['Cliente_Contrato_Antigo'] = df['Fluxo Contrato']
        df['Cliente_Novo_Contrato']   = df.apply(
            lambda row: row['Fluxo Mercado'] if row['Data_Obj'] >= data_pagamento else 0.0,
            axis=1
        )

        df['Cliente_Fluxo_Final'] = df.apply(
            lambda row: -row['Cliente_Contrato_Antigo']
            if row['Data_Obj'] < data_pagamento
            else -row['Cliente_Contrato_Antigo'] - row['Cliente_Novo_Contrato'],
            axis=1
        )
        df.loc[idx_pag, 'Cliente_Fluxo_Final'] = (
            pagamento_unico
            - df.loc[idx_pag, 'Cliente_Contrato_Antigo']
            - df.loc[idx_pag, 'Cliente_Novo_Contrato']
        )

        df['Genial_Recebe_Mensal'] = df.apply(
            lambda row: row['Fluxo Mercado'] if row['Data_Obj'] >= data_pagamento else 0.0,
            axis=1
        )

    elif modo_operacao == "modo_a":

        # VP relativo ao mês de pagamento, de TODOS os meses (incluindo os anteriores ao pagamento)
        df['Cliente_Recebe_VP'] = df['Fluxo Mercado'] / df['Fator_Desconto_Relativo']
        pagamento_unico = df['Cliente_Recebe_VP'].sum()

        df['Cliente_Contrato_Antigo'] = df['Fluxo Contrato']
        # Cliente paga mercado desde o início
        df['Cliente_Novo_Contrato'] = df['Fluxo Mercado']

        # Fluxo mensal: paga contrato antigo + mercado todos os meses
        df['Cliente_Fluxo_Final'] = -df['Cliente_Contrato_Antigo'] - df['Cliente_Novo_Contrato']
        # No mês do pagamento: adiciona o recebimento único
        df.loc[idx_pag, 'Cliente_Fluxo_Final'] = (
            pagamento_unico
            - df.loc[idx_pag, 'Cliente_Contrato_Antigo']
            - df.loc[idx_pag, 'Cliente_Novo_Contrato']
        )

        # Genial recebe mercado desde o início (pois o cliente paga desde o início)
        df['Genial_Recebe_Mensal'] = df['Fluxo Mercado']

    elif modo_operacao == "modo_b":

        # Fator do mês de início (mês 1) para descontar ao início
        du_inicio = 1 * 21
        cdi_inicio = interpolar_flat_forward(du_inicio, curva_anbima)
        fator_inicio = ((1 + cdi_inicio) * (1 + spread)) ** (du_inicio / 252)
        # Fator relativo ao mês de início
        df['Fator_Desconto_Rel_Inicio'] = df['Fator_Desconto'] / fator_inicio

        # VP calculado apenas para meses a partir do mês de pagamento, descontado ao início
        df['Cliente_Recebe_VP'] = df.apply(
            lambda row: row['Fluxo Mercado'] / row['Fator_Desconto_Rel_Inicio'] if row['Data_Obj'] >= data_pagamento else 0.0,
            axis=1
        )
        pagamento_unico = df['Cliente_Recebe_VP'].sum()

        df['Cliente_Contrato_Antigo'] = df['Fluxo Contrato']
        # Cliente só paga mercado a partir do mês de pagamento
        df['Cliente_Novo_Contrato'] = df.apply(
            lambda row: row['Fluxo Mercado'] if row['Data_Obj'] >= data_pagamento else 0.0,
            axis=1
        )

        # Fluxo mensal:
        # - Antes do pagamento: apenas contrato antigo (sem aditivo de mercado)
        # - A partir do pagamento: contrato antigo + mercado
        df['Cliente_Fluxo_Final'] = df.apply(
            lambda row: -row['Cliente_Contrato_Antigo']
            if row['Data_Obj'] < data_pagamento
            else -row['Cliente_Contrato_Antigo'] - row['Cliente_Novo_Contrato'],
            axis=1
        )
        # No mês de início (mês 1): cliente recebe o pagamento único antecipado
        idx_inicio = df.index[0]
        df.loc[idx_inicio, 'Cliente_Fluxo_Final'] = (
            pagamento_unico
            - df.loc[idx_inicio, 'Cliente_Contrato_Antigo']
            # sem mercado antes do pagamento
        )

        # Genial recebe mercado apenas a partir do mês de pagamento
        df['Genial_Recebe_Mensal'] = df.apply(
            lambda row: row['Fluxo Mercado'] if row['Data_Obj'] >= data_pagamento else 0.0,
            axis=1
        )

    df['Peso_MWh'] = df['Horas'] * df['Volume']

    resumo_anual = df.groupby('Ano').apply(lambda g: pd.Series({
        'MWh Total':            g['Peso_MWh'].sum(),
        'Cliente_Recebe_VP':    g['Cliente_Recebe_VP'].sum(),
        'Cliente_Paga_VP':      g['Fluxo Mercado'].sum(),
        'Genial_Recebe_Mensal': g['Genial_Recebe_Mensal'].sum(),
    })).reset_index()

    resumo_anual['Preço Venda Cliente (R$/MWh)']  = resumo_anual['Cliente_Recebe_VP']    / resumo_anual['MWh Total']
    resumo_anual['Preço Compra Cliente (R$/MWh)'] = resumo_anual['Cliente_Paga_VP']      / resumo_anual['MWh Total']
    resumo_anual['Preço Recebe Genial (R$/MWh)']  = resumo_anual['Genial_Recebe_Mensal'] / resumo_anual['MWh Total']
    resumo_anual['Preço Contrato Input (R$/MWh)'] = resumo_anual['Ano'].map(lambda x: dados_operacao[x]['contrato'])

    st.subheader("👤 Visão Cliente")

    if modo_operacao == "padrao":
        st.caption(f"A Genial paga ao cliente o valor presente de toda a operação em uma única parcela em **{pagamento_str}**.")
    elif modo_operacao == "modo_a":
        st.caption(f"Cliente paga o aditivo de mercado **desde {inicio_str}**. A Genial paga o VP de toda a operação em uma única parcela em **{pagamento_str}**.")
    elif modo_operacao == "modo_b":
        st.caption(f"A Genial paga ao cliente o VP antecipado em **{inicio_str}** (referente ao período {pagamento_str} → {fim_str}). Cliente não paga aditivo até {pagamento_str}, quando passa a pagar o novo contrato de mercado.")

    if contrato_genial:
        st.info("""
**🏦 Contrato Genial**

A operação funciona da seguinte forma:
- A Genial **aditiva o contrato original** para preços de mercado
- O cliente **vende um contrato à Genial** ao preço de venda calculado
- O pagamento ao cliente ocorre de forma **integral e antecipada em M+0** (pagamento único à vista)
- O cliente deve fazer o **registro antecipado do volume negociado na CCEE** a favor da Genial
        """)
    else:
        st.info("""
**📄 Contrato Externo**

A operação funciona da seguinte forma:
- O cliente **cede seu contrato de compra** de energia à Genial
- O cliente **vende um contrato à Genial** ao preço de venda calculado
- O pagamento ao cliente ocorre de forma **integral e antecipada em M+0** (pagamento único à vista)
- A partir daí, o cliente passa a **comprar energia da Genial a preços de mercado**, com liquidação registrada mensalmente
- O cliente deve fazer o **registro antecipado do volume negociado na CCEE** a favor da Genial
        """)

    c1, c2, c3 = st.columns(3)
    c1.metric("Contrato Original (total)", f"R$ {formatar_moeda_abrev(-df['Cliente_Contrato_Antigo'].sum())}")
    c2.metric("Recebe da Genial (único)",  f"R$ {formatar_moeda_abrev(pagamento_unico)}")
    c3.metric("Novo Contrato (total)",     f"R$ {formatar_moeda_abrev(-df['Cliente_Novo_Contrato'].sum())}")

    st.markdown("**📅 Fluxo Mensal do Cliente**")
    df_cliente = df[['mês', 'Volume', 'Cliente_Contrato_Antigo', 'Cliente_Novo_Contrato', 'Cliente_Fluxo_Final']].copy()
    df_cliente['Cliente_Contrato_Antigo'] = -df_cliente['Cliente_Contrato_Antigo']
    df_cliente['Cliente_Novo_Contrato']   = -df_cliente['Cliente_Novo_Contrato']
    df_cliente = df_cliente.rename(columns={
        'Volume':                  'Volume (MWm)',
        'Cliente_Contrato_Antigo': 'Contrato Antigo (R$)',
        'Cliente_Novo_Contrato':   'Novo Contrato (R$)',
        'Cliente_Fluxo_Final':     'Fluxo Final (R$)',
    })

    st.dataframe(df_cliente.style
        .format({
            'Volume (MWm)':         '{:.2f}',
            'Contrato Antigo (R$)': 'R$ {:,.2f}',
            'Novo Contrato (R$)':   'R$ {:,.2f}',
            'Fluxo Final (R$)':     'R$ {:,.2f}',
        })
        .applymap(colorir_fluxo, subset=['Fluxo Final (R$)']),
    use_container_width=True)

    st.markdown("**📋 Preço de Venda do Contrato — Cliente**")
    st.caption("Preço médio ponderado anual pelo qual o cliente vende o contrato à Genial (R$/MWh)")
    df_preco_venda_cliente = resumo_anual[['Ano', 'Preço Contrato Input (R$/MWh)', 'Preço Venda Cliente (R$/MWh)']].rename(columns={
        'Preço Contrato Input (R$/MWh)': 'Preço Pago no Contrato (R$/MWh)',
        'Preço Venda Cliente (R$/MWh)':  'Preço de Venda à Genial (R$/MWh)',
    })
    st.dataframe(df_preco_venda_cliente.style.format({
        'Preço Pago no Contrato (R$/MWh)':  'R$ {:.2f}',
        'Preço de Venda à Genial (R$/MWh)': 'R$ {:.2f}',
    }), use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("🏦 Visão Genial Investimentos")

    if modo_operacao == "padrao":
        st.caption(f"Genial **paga** ao cliente o VP total em **{pagamento_str}** e **recebe** mensalmente o valor de mercado a partir de {pagamento_str}.")
    elif modo_operacao == "modo_a":
        st.caption(f"Genial **paga** ao cliente o VP total em **{pagamento_str}** e **recebe** mensalmente o valor de mercado **desde {inicio_str}**.")
    elif modo_operacao == "modo_b":
        st.caption(f"Genial **paga** ao cliente o VP antecipado em **{inicio_str}** e **recebe** mensalmente o valor de mercado a partir de **{pagamento_str}**.")

    desembolso_genial = pagamento_unico

    df_genial = df[['mês', 'Data_Obj', 'Volume', 'Genial_Recebe_Mensal']].copy()
    df_genial['Genial_Desembolso'] = 0.0

    if modo_operacao == "modo_b":
        # Desembolso no primeiro mês
        df_genial.loc[df_genial.index[0], 'Genial_Desembolso'] = -desembolso_genial
    else:
        # Desembolso no mês de pagamento
        df_genial.loc[idx_pag, 'Genial_Desembolso'] = -desembolso_genial

    df_genial['Genial_Fluxo_Final'] = df_genial['Genial_Recebe_Mensal'] + df_genial['Genial_Desembolso']
    lucro_genial = df_genial['Genial_Fluxo_Final'].sum()

    g1, g2, g3 = st.columns(3)
    g1.metric("Recebe (total futuro)",    f"R$ {formatar_moeda_abrev(df_genial['Genial_Recebe_Mensal'].sum())}")
    g2.metric("Desembolso na Cabeça",     f"R$ {formatar_moeda_abrev(-desembolso_genial)}")
    g3.metric("Resultado Líquido",        f"R$ {formatar_moeda_abrev(lucro_genial)}")

    st.markdown("**📅 Fluxo Mensal da Genial**")
    df_genial_disp = df_genial.drop(columns=['Data_Obj']).rename(columns={
        'Volume':               'Volume (MWm)',
        'Genial_Recebe_Mensal': 'Recebe Mercado (R$)',
        'Genial_Fluxo_Final':   'Fluxo Final (R$)',
    })

    st.dataframe(df_genial_disp[['mês', 'Volume (MWm)', 'Recebe Mercado (R$)', 'Fluxo Final (R$)']].style
        .format({
            'Volume (MWm)':        '{:.2f}',
            'Recebe Mercado (R$)': 'R$ {:,.2f}',
            'Fluxo Final (R$)':    'R$ {:,.2f}',
        })
        .applymap(colorir_fluxo, subset=['Fluxo Final (R$)']),
    use_container_width=True)

    st.markdown("**📋 Preço de Recebimento Médio — Genial**")
    st.caption("Preço médio ponderado anual recebido pela Genial via contratos de mercado (R$/MWh)")
    df_preco_genial = resumo_anual[['Ano', 'Preço Recebe Genial (R$/MWh)']].rename(columns={
        'Preço Recebe Genial (R$/MWh)': 'Preço de Recebimento (R$/MWh)',
    })
    st.dataframe(df_preco_genial.style.format({
        'Preço de Recebimento (R$/MWh)': 'R$ {:.2f}',
    }), use_container_width=True, hide_index=True)

    st.divider()

    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Exportar para CSV", csv, "calculo_energia.csv", "text/csv", use_container_width=True)

else:
    st.write("---")
    st.caption("Aguardando comando...")