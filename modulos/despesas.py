"""Interface do módulo Despesas (gastos fora do cartão de crédito)."""

from datetime import date

import streamlit as st

from components.formatacao import formatar_moeda
from database import db


MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def _mostrar_mensagem():
    mensagem = st.session_state.pop("mensagem_despesas", None)
    if mensagem:
        st.success(mensagem)


def _formatar_data(valor):
    if not valor:
        return "Não informada"
    try:
        return date.fromisoformat(str(valor)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(valor)


def _situacao_visual(status, tem_vencimento, vencimento):
    if status == "Pago":
        return "Pago"
    if tem_vencimento and vencimento and vencimento < date.today().isoformat():
        return "Atrasada"
    return "Pendente"


def _opcoes_referencia(despesas):
    referencias = sorted(
        {d[8] for d in despesas if d[8]},
        reverse=True,
    )
    return ["Todas"] + referencias


def _mostrar_formulario_nova_despesa():
    st.subheader("Registrar despesa")
    st.caption(
        "Use esta área para gastos em dinheiro, PIX, débito, boletos, "
        "transferências e outros meios. Compras no crédito ficam em Cartões."
    )

    hoje = date.today()
    categorias = db.listar_categorias()
    anos = list(range(hoje.year - 1, hoje.year + 11))

    col_estado, col_vencimento = st.columns(2)
    with col_estado:
        situacao_inicial = st.radio(
            "Situação da despesa",
            ["Pendente", "Pago"],
            horizontal=True,
            key="nova_despesa_situacao",
            help="Indique se a despesa já foi paga ou ainda está em aberto.",
        )
    with col_vencimento:
        possui_vencimento = st.checkbox(
            "Esta despesa possui vencimento?",
            value=False,
            key="nova_despesa_tem_vencimento",
        )

    with st.form("form_nova_despesa", clear_on_submit=True):
        descricao = st.text_input("Descrição", placeholder="Ex.: Compra no supermercado")

        col1, col2 = st.columns(2)
        with col1:
            valor = st.number_input(
                "Valor (R$)", min_value=0.01, value=0.01,
                step=10.00, format="%.2f",
            )
            categoria = st.selectbox("Categoria", categorias)
            forma_pagamento = st.selectbox(
                "Forma de pagamento",
                db.FORMAS_PAGAMENTO,
                help="Não inclua compras feitas no crédito. Elas são registradas em Cartões.",
            )
        with col2:
            data_despesa = st.date_input(
                "Data da despesa", value=hoje, format="DD/MM/YYYY",
                help="Dia em que o gasto aconteceu ou foi contratado.",
            )
            vencimento = None
            if possui_vencimento:
                vencimento = st.date_input(
                    "Data de vencimento", value=hoje, format="DD/MM/YYYY",
                )
            data_pagamento = None
            if situacao_inicial == "Pago":
                data_pagamento = st.date_input(
                    "Data do pagamento", value=hoje, format="DD/MM/YYYY",
                )

        st.markdown("**Mês de referência**")
        col_mes, col_ano = st.columns(2)
        with col_mes:
            mes_referencia = st.selectbox(
                "Mês", options=list(range(1, 13)),
                format_func=lambda mes: MESES[mes - 1],
                index=hoje.month - 1,
            )
        with col_ano:
            ano_referencia = st.selectbox(
                "Ano", options=anos, index=anos.index(hoje.year),
            )

        salvar = st.form_submit_button(
            "Salvar despesa", use_container_width=True,
        )

    if salvar:
        if not descricao.strip():
            st.error("Informe a descrição da despesa.")
            return

        try:
            db.adicionar_despesa(
                descricao=descricao,
                valor=valor,
                categoria=categoria,
                forma_pagamento=forma_pagamento,
                data_despesa=data_despesa.isoformat(),
                tem_vencimento=possui_vencimento,
                vencimento=vencimento.isoformat() if vencimento else None,
                referencia=f"{ano_referencia}-{mes_referencia:02d}",
                status=situacao_inicial,
                data_pagamento=data_pagamento.isoformat() if data_pagamento else None,
            )
            st.session_state["mensagem_despesas"] = "Despesa cadastrada com sucesso!"
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))


def _mostrar_categorias():
    with st.expander("➕ Adicionar nova categoria"):
        with st.form("form_nova_categoria_despesa"):
            nome_categoria = st.text_input("Nome da categoria")
            salvar_categoria = st.form_submit_button(
                "Salvar categoria", use_container_width=True,
            )

        if salvar_categoria:
            if not nome_categoria.strip():
                st.error("Informe o nome da categoria.")
            elif db.adicionar_categoria(nome_categoria):
                st.session_state["mensagem_despesas"] = "Categoria adicionada com sucesso!"
                st.rerun()
            else:
                st.warning("Essa categoria já existe.")


def _mostrar_filtros(despesas):
    st.subheader("Filtrar despesas")
    metodos_existentes = sorted({d[4] for d in despesas if d[4]})
    metodos = ["Todas"] + metodos_existentes
    categorias = ["Todas"] + db.listar_categorias()
    situacoes = ["Todas", "Pago", "Pendente"]
    referencias = _opcoes_referencia(despesas)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        filtro_metodo = st.selectbox("Forma de pagamento", metodos, key="filtro_despesa_metodo")
    with c2:
        filtro_categoria = st.selectbox("Categoria", categorias, key="filtro_despesa_categoria")
    with c3:
        filtro_situacao = st.selectbox("Situação", situacoes, key="filtro_despesa_situacao")
    with c4:
        filtro_referencia = st.selectbox(
            "Mês de referência", referencias, key="filtro_despesa_referencia",
        )

    return db.listar_despesas(
        forma_pagamento=filtro_metodo,
        categoria=filtro_categoria,
        status=filtro_situacao,
        referencia=filtro_referencia,
    )


def _mostrar_linha_despesa(despesa, arquivada=False):
    (
        id_despesa, descricao, valor, categoria, forma_pagamento,
        data_despesa, tem_vencimento, vencimento, referencia,
        status, pago_em, _arquivada,
    ) = despesa

    situacao_visual = _situacao_visual(status, tem_vencimento, vencimento)
    col_desc, col_valor, col_status, col_acoes = st.columns(
        [3.3, 1.35, 1.15, 2.6 if not arquivada else 1.35],
        vertical_alignment="center",
    )

    with col_desc:
        st.write(f"**{descricao}**")
        detalhes = [categoria, forma_pagamento]
        if data_despesa:
            detalhes.append(f"Despesa: {_formatar_data(data_despesa)}")
        else:
            detalhes.append("Data da despesa não informada")
        if tem_vencimento:
            detalhes.append(f"Vence: {_formatar_data(vencimento)}")
        else:
            detalhes.append("Sem vencimento")
        if status == "Pago" and pago_em:
            detalhes.append(f"Pago em: {_formatar_data(pago_em)}")
        if referencia:
            detalhes.append(f"Referência: {referencia}")
        st.caption(" · ".join(detalhes))

    with col_valor:
        st.write(formatar_moeda(valor))

    with col_status:
        if situacao_visual == "Pago":
            st.success("Pago")
        elif situacao_visual == "Atrasada":
            st.error("Atrasada")
        else:
            st.warning("Pendente")

    with col_acoes:
        if arquivada:
            if st.button("Restaurar", key=f"restaurar_despesa_{id_despesa}", use_container_width=True):
                if db.restaurar_conta(id_despesa):
                    st.session_state["mensagem_despesas"] = "Despesa restaurada para a lista ativa."
                    st.rerun()
        else:
            a1, a2, a3 = st.columns(3)
            with a1:
                if status == "Pago":
                    if st.button("Pendente", key=f"pendente_despesa_{id_despesa}", use_container_width=True):
                        if db.marcar_como_pendente(id_despesa):
                            st.session_state["mensagem_despesas"] = "Despesa reaberta como pendente."
                            st.rerun()
                else:
                    if st.button("Pagar", key=f"pagar_despesa_{id_despesa}", use_container_width=True):
                        if db.marcar_como_paga(id_despesa, date.today().isoformat()):
                            st.session_state["mensagem_despesas"] = "Pagamento registrado."
                            st.rerun()
            with a2:
                if st.button("Editar", key=f"editar_despesa_{id_despesa}", use_container_width=True):
                    st.session_state["despesa_em_edicao"] = id_despesa
                    st.session_state[f"editar_despesa_tem_vencimento_{id_despesa}"] = bool(tem_vencimento)
                    st.rerun()
            with a3:
                if st.button("Arquivar", key=f"arquivar_despesa_{id_despesa}", use_container_width=True):
                    if db.arquivar_conta(id_despesa):
                        st.session_state["despesa_em_edicao"] = None
                        st.session_state["mensagem_despesas"] = "Despesa arquivada. O histórico foi preservado."
                        st.rerun()


def _mostrar_editor():
    id_edicao = st.session_state.get("despesa_em_edicao")
    if id_edicao is None:
        return

    dados = db.obter_despesa(id_edicao)
    if dados is None or dados[11] == 1:
        st.session_state["despesa_em_edicao"] = None
        st.warning("A despesa selecionada não está mais disponível para edição.")
        return

    (
        id_despesa, descricao, valor, categoria, forma_pagamento,
        data_despesa, tem_vencimento_atual, vencimento, referencia,
        status, pago_em, arquivada,
    ) = dados

    if not referencia:
        referencia = (data_despesa or vencimento)[:7]
    ano_ref, mes_ref = map(int, referencia.split("-"))
    hoje = date.today()
    anos = list(range(min(hoje.year - 1, ano_ref), max(hoje.year + 10, ano_ref) + 1))
    categorias = db.listar_categorias()
    if categoria not in categorias:
        categorias.append(categoria)
        categorias.sort()
    metodos = list(db.FORMAS_PAGAMENTO)
    if forma_pagamento not in metodos:
        metodos.append(forma_pagamento)

    st.divider()
    st.subheader(f"Editar despesa: {descricao}")

    chave_vencimento = f"editar_despesa_tem_vencimento_{id_despesa}"
    if chave_vencimento not in st.session_state:
        st.session_state[chave_vencimento] = bool(tem_vencimento_atual)
    possui_vencimento = st.checkbox(
        "Esta despesa possui vencimento?",
        key=chave_vencimento,
    )

    if not data_despesa:
        st.info(
            "Este lançamento é anterior ao registro da data da despesa. "
            "O campo abaixo começa com a data de vencimento antiga como referência; "
            "ajuste-a caso conheça a data real."
        )
    data_despesa_inicial = data_despesa or vencimento

    with st.form(f"form_editar_despesa_{id_despesa}"):
        descricao_nova = st.text_input("Descrição", value=descricao)
        col1, col2 = st.columns(2)
        with col1:
            valor_novo = st.number_input(
                "Valor (R$)", min_value=0.01, value=float(valor),
                step=10.00, format="%.2f",
            )
            categoria_nova = st.selectbox(
                "Categoria", categorias, index=categorias.index(categoria),
            )
            forma_nova = st.selectbox(
                "Forma de pagamento", metodos, index=metodos.index(forma_pagamento),
            )
        with col2:
            data_nova = st.date_input(
                "Data da despesa", value=date.fromisoformat(data_despesa_inicial),
                format="DD/MM/YYYY",
            )
            vencimento_novo = None
            if possui_vencimento:
                vencimento_novo = st.date_input(
                    "Data de vencimento", value=date.fromisoformat(vencimento),
                    format="DD/MM/YYYY",
                )

        st.markdown("**Mês de referência**")
        c_mes, c_ano = st.columns(2)
        with c_mes:
            mes_novo = st.selectbox(
                "Mês", list(range(1, 13)), format_func=lambda m: MESES[m - 1],
                index=mes_ref - 1,
            )
        with c_ano:
            ano_novo = st.selectbox(
                "Ano", anos, index=anos.index(ano_ref),
            )
        st.caption(f"Situação atual: {status}. A alteração do pagamento é feita na lista de despesas.")
        salvar = st.form_submit_button("Salvar alterações", use_container_width=True)

    c_salvar, c_cancelar = st.columns([1, 4])
    with c_cancelar:
        cancelar = st.button("Cancelar edição", key=f"cancelar_despesa_{id_despesa}")

    if salvar:
        if not descricao_nova.strip():
            st.error("Informe a descrição da despesa.")
        else:
            try:
                atualizada = db.editar_despesa(
                    id_despesa, descricao_nova, valor_novo, categoria_nova,
                    forma_nova, data_nova.isoformat(), possui_vencimento,
                    vencimento_novo.isoformat() if vencimento_novo else None,
                    f"{ano_novo}-{mes_novo:02d}",
                )
                if atualizada:
                    st.session_state["despesa_em_edicao"] = None
                    st.session_state["mensagem_despesas"] = "Despesa atualizada com sucesso!"
                    st.rerun()
                else:
                    st.error("Não foi possível localizar a despesa para atualizar.")
            except ValueError as erro:
                st.error(str(erro))

    if cancelar:
        st.session_state["despesa_em_edicao"] = None
        st.rerun()


def mostrar_despesas():
    """Renderiza a área de despesas pagas ou pendentes fora do crédito."""
    if "despesa_em_edicao" not in st.session_state:
        st.session_state["despesa_em_edicao"] = None

    st.title("Despesas")
    st.caption("Organize gastos em dinheiro, PIX, débito, boletos e transferências. Compras no crédito ficam em Cartões.")
    _mostrar_mensagem()

    _mostrar_formulario_nova_despesa()
    _mostrar_categorias()
    st.divider()

    todas_ativas = db.listar_despesas()
    arquivadas = db.listar_despesas(arquivada=True)
    despesas_filtradas = _mostrar_filtros(todas_ativas) if todas_ativas else []

    aba_ativas, aba_arquivadas = st.tabs([
        f"Despesas ativas ({len(todas_ativas)})",
        f"Arquivadas ({len(arquivadas)})",
    ])

    with aba_ativas:
        total_pendente = sum(d[2] for d in despesas_filtradas if d[9] == "Pendente")
        total_pago = sum(d[2] for d in despesas_filtradas if d[9] == "Pago")
        m1, m2, m3 = st.columns(3)
        m1.metric("Despesas exibidas", len(despesas_filtradas))
        m2.metric("Em aberto", formatar_moeda(total_pendente))
        m3.metric("Pagas", formatar_moeda(total_pago))

        st.subheader("Lançamentos")
        if despesas_filtradas:
            for despesa in despesas_filtradas:
                _mostrar_linha_despesa(despesa)
                st.divider()
        else:
            st.info("Nenhuma despesa corresponde aos filtros selecionados.")
        _mostrar_editor()

    with aba_arquivadas:
        st.subheader("Despesas arquivadas")
        st.caption("Os lançamentos arquivados permanecem no histórico e podem ser restaurados.")
        if arquivadas:
            for despesa in arquivadas:
                _mostrar_linha_despesa(despesa, arquivada=True)
                st.divider()
        else:
            st.info("Nenhuma despesa arquivada.")
