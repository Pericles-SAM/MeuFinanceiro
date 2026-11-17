"""Regras de negócio e persistência do módulo de cartões de crédito.

Valores monetários são armazenados em centavos (INTEGER) para evitar
imprecisão de ponto flutuante. O arquivo antigo `faturas` é preservado e
migrado de forma idempotente para o novo modelo de faturas mensais.
"""

from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from unicodedata import normalize

from database.db import conectar


MAX_PARCELAS = 48
TIPOS_AJUSTE = {"Encargo", "Crédito"}


def _data_iso(valor):
    if isinstance(valor, date):
        return valor.isoformat()
    try:
        return date.fromisoformat(str(valor)).isoformat()
    except (TypeError, ValueError):
        raise ValueError("Informe uma data válida no formato AAAA-MM-DD.")


def _centavos(valor):
    try:
        decimal = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Informe um valor monetário válido.")
    if decimal <= 0:
        raise ValueError("O valor deve ser maior que zero.")
    return int(decimal * 100)


def _adicionar_meses(ano, mes, quantidade):
    indice = (ano * 12 + (mes - 1)) + quantidade
    return indice // 12, indice % 12 + 1


def _data_do_dia(ano, mes, dia):
    ultimo_dia = monthrange(ano, mes)[1]
    return date(ano, mes, min(int(dia), ultimo_dia))


def _normalizar_regra(regra):
    regra = (regra or "proxima").strip().lower()
    if regra not in {"atual", "proxima"}:
        raise ValueError("Regra de fechamento inválida.")
    return regra


def calcular_ciclo_compra(data_compra, dia_fechamento, regra_fechamento="proxima"):
    """Retorna (ano, mês) da fatura da primeira parcela da compra.

    Compras antes do fechamento entram no ciclo do mês corrente. Compras
    depois do fechamento vão para o ciclo seguinte. No próprio dia do
    fechamento, o comportamento é configurável por cartão.
    """
    data_compra = date.fromisoformat(_data_iso(data_compra))
    dia_fechamento = int(dia_fechamento)
    if not 1 <= dia_fechamento <= 31:
        raise ValueError("Dia de fechamento inválido.")
    regra = _normalizar_regra(regra_fechamento)
    fechamento_efetivo = min(dia_fechamento, monthrange(data_compra.year, data_compra.month)[1])

    if data_compra.day < fechamento_efetivo:
        return data_compra.year, data_compra.month
    if data_compra.day == fechamento_efetivo and regra == "atual":
        return data_compra.year, data_compra.month
    return _adicionar_meses(data_compra.year, data_compra.month, 1)


def calcular_datas_fatura(ano, mes, dia_fechamento, dia_vencimento):
    """Calcula datas de fechamento e vencimento do ciclo mensal.

    Se o dia de vencimento for igual ou anterior ao de fechamento, entende-se
    que o vencimento ocorre no mês seguinte ao fechamento.
    Dias inexistentes (ex.: dia 31 em fevereiro) são ajustados para o último
    dia válido daquele mês.
    """
    ano, mes = int(ano), int(mes)
    dia_fechamento, dia_vencimento = int(dia_fechamento), int(dia_vencimento)
    if not 1 <= dia_fechamento <= 31 or not 1 <= dia_vencimento <= 31:
        raise ValueError("Os dias de fechamento e vencimento devem estar entre 1 e 31.")

    fechamento = _data_do_dia(ano, mes, dia_fechamento)
    if dia_vencimento > dia_fechamento:
        ano_venc, mes_venc = ano, mes
    else:
        ano_venc, mes_venc = _adicionar_meses(ano, mes, 1)
    vencimento = _data_do_dia(ano_venc, mes_venc, dia_vencimento)
    return fechamento.isoformat(), vencimento.isoformat()


def dividir_em_parcelas(valor_total, quantidade):
    """Divide em centavos, distribuindo eventual resto nas primeiras parcelas."""
    total = _centavos(valor_total)
    quantidade = int(quantidade)
    if not 1 <= quantidade <= MAX_PARCELAS:
        raise ValueError(f"A quantidade deve ficar entre 1 e {MAX_PARCELAS} parcelas.")
    if total < quantidade:
        raise ValueError("O valor total é muito baixo para essa quantidade de parcelas.")
    base, resto = divmod(total, quantidade)
    return [base + (1 if i < resto else 0) for i in range(quantidade)]


def _garantir_fatura(conexao, cartao, ano, mes, vencimento_override=None):
    id_cartao, nome, dia_fechamento, dia_vencimento, regra, ativo = cartao
    fechamento, vencimento = calcular_datas_fatura(
        ano, mes, dia_fechamento, dia_vencimento
    )
    if vencimento_override:
        vencimento = _data_iso(vencimento_override)

    conexao.execute(
        """INSERT OR IGNORE INTO faturas_cartao
           (cartao_id, ano, mes, data_fechamento, data_vencimento)
           VALUES (?, ?, ?, ?, ?)""",
        (id_cartao, int(ano), int(mes), fechamento, vencimento),
    )
    return conexao.execute(
        "SELECT id FROM faturas_cartao WHERE cartao_id = ? AND ano = ? AND mes = ?",
        (id_cartao, int(ano), int(mes)),
    ).fetchone()[0]


def _cartao(conexao, id_cartao, incluir_inativo=True):
    filtro = "" if incluir_inativo else " AND ativo = 1"
    resultado = conexao.execute(
        f"""SELECT id, nome, dia_fechamento, dia_vencimento,
                   regra_fechamento, ativo
            FROM cartoes WHERE id = ?{filtro}""",
        (id_cartao,),
    ).fetchone()
    if not resultado:
        raise ValueError("O cartão selecionado não foi encontrado ou está inativo.")
    return resultado


def _criar_parcelas(conexao, id_compra, cartao, data_compra, valores_centavos, versao=1):
    _, _, dia_fechamento, dia_vencimento, regra, _ = cartao
    ano_inicial, mes_inicial = calcular_ciclo_compra(
        data_compra, dia_fechamento, regra
    )
    total_parcelas = len(valores_centavos)

    for indice, valor_centavos in enumerate(valores_centavos, start=1):
        ano, mes = _adicionar_meses(ano_inicial, mes_inicial, indice - 1)
        id_fatura = _garantir_fatura(conexao, cartao, ano, mes)
        conexao.execute(
            """INSERT INTO parcelas_cartao
               (compra_id, fatura_id, numero_parcela, total_parcelas, valor_centavos, versao)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (id_compra, id_fatura, indice, total_parcelas, valor_centavos, versao),
        )


def inicializar_estrutura_cartoes():
    """Cria o novo modelo e importa faturas antigas sem excluir os originais."""
    with conectar() as conexao:
        colunas = {
            linha[1]
            for linha in conexao.execute("PRAGMA table_info(cartoes)").fetchall()
        }
        if "regra_fechamento" not in colunas:
            conexao.execute(
                "ALTER TABLE cartoes ADD COLUMN regra_fechamento TEXT NOT NULL DEFAULT 'proxima'"
            )
        if "ativo" not in colunas:
            conexao.execute(
                "ALTER TABLE cartoes ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1"
            )

        conexao.executescript("""
            CREATE TABLE IF NOT EXISTS faturas_cartao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cartao_id INTEGER NOT NULL,
                ano INTEGER NOT NULL,
                mes INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
                data_fechamento TEXT NOT NULL,
                data_vencimento TEXT NOT NULL,
                criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                UNIQUE (cartao_id, ano, mes),
                FOREIGN KEY (cartao_id) REFERENCES cartoes(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS compras_cartao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cartao_id INTEGER NOT NULL,
                descricao TEXT NOT NULL,
                categoria TEXT,
                data_compra TEXT NOT NULL,
                valor_total_centavos INTEGER NOT NULL CHECK (valor_total_centavos > 0),
                numero_parcelas INTEGER NOT NULL CHECK (numero_parcelas BETWEEN 1 AND 48),
                observacao TEXT,
                ativa INTEGER NOT NULL DEFAULT 1,
                versao_atual INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (cartao_id) REFERENCES cartoes(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS parcelas_cartao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compra_id INTEGER NOT NULL,
                fatura_id INTEGER NOT NULL,
                numero_parcela INTEGER NOT NULL,
                total_parcelas INTEGER NOT NULL,
                valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
                versao INTEGER NOT NULL DEFAULT 1,
                ativa INTEGER NOT NULL DEFAULT 1,
                cancelada_em TEXT,
                motivo_cancelamento TEXT,
                criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (compra_id) REFERENCES compras_cartao(id) ON DELETE RESTRICT,
                FOREIGN KEY (fatura_id) REFERENCES faturas_cartao(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS compras_cartao_historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compra_id INTEGER NOT NULL,
                cartao_id INTEGER NOT NULL,
                descricao TEXT NOT NULL,
                categoria TEXT,
                data_compra TEXT NOT NULL,
                valor_total_centavos INTEGER NOT NULL,
                numero_parcelas INTEGER NOT NULL,
                observacao TEXT,
                alterado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                motivo_alteracao TEXT,
                FOREIGN KEY (compra_id) REFERENCES compras_cartao(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS ajustes_fatura (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fatura_id INTEGER NOT NULL,
                tipo TEXT NOT NULL CHECK (tipo IN ('Encargo', 'Crédito', 'Legado')),
                descricao TEXT NOT NULL,
                valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
                criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                cancelado INTEGER NOT NULL DEFAULT 0,
                cancelado_em TEXT,
                motivo_cancelamento TEXT,
                FOREIGN KEY (fatura_id) REFERENCES faturas_cartao(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS pagamentos_fatura (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fatura_id INTEGER NOT NULL,
                valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
                data_pagamento TEXT,
                observacao TEXT,
                criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                estornado INTEGER NOT NULL DEFAULT 0,
                estornado_em TEXT,
                motivo_estorno TEXT,
                FOREIGN KEY (fatura_id) REFERENCES faturas_cartao(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS faturas_antigas_importadas (
                id_fatura_antiga INTEGER PRIMARY KEY,
                id_fatura_nova INTEGER NOT NULL,
                FOREIGN KEY (id_fatura_nova) REFERENCES faturas_cartao(id) ON DELETE RESTRICT
            );

            CREATE INDEX IF NOT EXISTS idx_faturas_cartao_vencimento
                ON faturas_cartao(data_vencimento);
            CREATE INDEX IF NOT EXISTS idx_compras_cartao_data
                ON compras_cartao(data_compra);
            CREATE INDEX IF NOT EXISTS idx_parcelas_fatura
                ON parcelas_cartao(fatura_id);
            CREATE INDEX IF NOT EXISTS idx_pagamentos_fatura
                ON pagamentos_fatura(fatura_id);
        """)

        # Migração incremental para bancos que já tenham criado as tabelas novas.
        colunas_compras = {
            linha[1] for linha in conexao.execute("PRAGMA table_info(compras_cartao)").fetchall()
        }
        if "versao_atual" not in colunas_compras:
            conexao.execute("ALTER TABLE compras_cartao ADD COLUMN versao_atual INTEGER NOT NULL DEFAULT 1")

        colunas_parcelas = {
            linha[1] for linha in conexao.execute("PRAGMA table_info(parcelas_cartao)").fetchall()
        }
        for coluna, comando in {
            "versao": "ALTER TABLE parcelas_cartao ADD COLUMN versao INTEGER NOT NULL DEFAULT 1",
            "ativa": "ALTER TABLE parcelas_cartao ADD COLUMN ativa INTEGER NOT NULL DEFAULT 1",
            "cancelada_em": "ALTER TABLE parcelas_cartao ADD COLUMN cancelada_em TEXT",
            "motivo_cancelamento": "ALTER TABLE parcelas_cartao ADD COLUMN motivo_cancelamento TEXT",
        }.items():
            if coluna not in colunas_parcelas:
                conexao.execute(comando)

        conexao.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_parcela_compra_numero_ativa
            ON parcelas_cartao(compra_id, numero_parcela) WHERE ativa = 1""")

        colunas_ajustes = {
            linha[1] for linha in conexao.execute("PRAGMA table_info(ajustes_fatura)").fetchall()
        }
        for coluna, comando in {
            "cancelado": "ALTER TABLE ajustes_fatura ADD COLUMN cancelado INTEGER NOT NULL DEFAULT 0",
            "cancelado_em": "ALTER TABLE ajustes_fatura ADD COLUMN cancelado_em TEXT",
            "motivo_cancelamento": "ALTER TABLE ajustes_fatura ADD COLUMN motivo_cancelamento TEXT",
        }.items():
            if coluna not in colunas_ajustes:
                conexao.execute(comando)

        colunas_pagamentos = {
            linha[1] for linha in conexao.execute("PRAGMA table_info(pagamentos_fatura)").fetchall()
        }
        for coluna, comando in {
            "estornado": "ALTER TABLE pagamentos_fatura ADD COLUMN estornado INTEGER NOT NULL DEFAULT 0",
            "estornado_em": "ALTER TABLE pagamentos_fatura ADD COLUMN estornado_em TEXT",
            "motivo_estorno": "ALTER TABLE pagamentos_fatura ADD COLUMN motivo_estorno TEXT",
        }.items():
            if coluna not in colunas_pagamentos:
                conexao.execute(comando)

        # Migração do cadastro antigo de faturas: cada fatura antiga entra como
        # um item legado na fatura mensal correspondente. Os originais ficam intactos.
        antigas = conexao.execute("""
            SELECT f.id, f.cartao_id, f.valor, f.vencimento, f.status, f.pago_em,
                   c.dia_fechamento, c.dia_vencimento, c.nome
            FROM faturas f
            JOIN cartoes c ON c.id = f.cartao_id
            LEFT JOIN faturas_antigas_importadas m ON m.id_fatura_antiga = f.id
            WHERE m.id_fatura_antiga IS NULL
            ORDER BY f.id
        """).fetchall()

        for (id_antiga, id_cartao, valor, vencimento, status, pago_em,
             dia_fechamento, dia_vencimento, nome_cartao) in antigas:
            data_venc = date.fromisoformat(vencimento)
            if data_venc.day > int(dia_fechamento):
                ano_ciclo, mes_ciclo = data_venc.year, data_venc.month
            else:
                ano_ciclo, mes_ciclo = _adicionar_meses(data_venc.year, data_venc.month, -1)

            cartao = _cartao(conexao, id_cartao)
            id_fatura_nova = _garantir_fatura(
                conexao, cartao, ano_ciclo, mes_ciclo, vencimento_override=vencimento
            )
            centavos = _centavos(valor)
            conexao.execute(
                """INSERT INTO ajustes_fatura
                   (fatura_id, tipo, descricao, valor_centavos)
                   VALUES (?, 'Legado', ?, ?)""",
                (id_fatura_nova, f"Fatura antiga importada #{id_antiga} — {nome_cartao}", centavos),
            )
            if status == "Pago":
                data_pagamento = pago_em[:10] if pago_em else None
                conexao.execute(
                    """INSERT INTO pagamentos_fatura
                       (fatura_id, valor_centavos, data_pagamento, observacao)
                       VALUES (?, ?, ?, ?)""",
                    (id_fatura_nova, centavos, data_pagamento, f"Pagamento migrado da fatura antiga #{id_antiga}"),
                )
            conexao.execute(
                "INSERT INTO faturas_antigas_importadas (id_fatura_antiga, id_fatura_nova) VALUES (?, ?)",
                (id_antiga, id_fatura_nova),
            )


def _nome_cartao_duplicado(conexao, nome, id_ignorar=None):
    nome_normalizado = normalize("NFKC", nome).casefold()
    existentes = conexao.execute("SELECT id, nome FROM cartoes").fetchall()
    return any(
        id_existente != id_ignorar
        and normalize("NFKC", nome_existente).casefold() == nome_normalizado
        for id_existente, nome_existente in existentes
    )


def listar_cartoes_credito(ativos=None):
    with conectar() as conexao:
        sql = """SELECT id, nome, dia_fechamento, dia_vencimento,
                        regra_fechamento, ativo
                 FROM cartoes"""
        parametros = ()
        if ativos is True:
            sql += " WHERE ativo = 1"
        elif ativos is False:
            sql += " WHERE ativo = 0"
        sql += " ORDER BY ativo DESC, nome COLLATE NOCASE"
        return conexao.execute(sql, parametros).fetchall()


def adicionar_cartao_credito(nome, dia_fechamento, dia_vencimento, regra_fechamento="proxima"):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do cartão.")
    dia_fechamento, dia_vencimento = int(dia_fechamento), int(dia_vencimento)
    if not 1 <= dia_fechamento <= 31 or not 1 <= dia_vencimento <= 31:
        raise ValueError("Os dias de fechamento e vencimento devem ficar entre 1 e 31.")
    regra = _normalizar_regra(regra_fechamento)
    with conectar() as conexao:
        if _nome_cartao_duplicado(conexao, nome):
            raise ValueError("Já existe um cartão cadastrado com esse nome.")
        cursor = conexao.execute(
            """INSERT INTO cartoes
               (nome, dia_fechamento, dia_vencimento, regra_fechamento, ativo)
               VALUES (?, ?, ?, ?, 1)""",
            (nome, dia_fechamento, dia_vencimento, regra),
        )
        return cursor.lastrowid


def editar_cartao_credito(id_cartao, nome, dia_fechamento, dia_vencimento, regra_fechamento):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do cartão.")
    dia_fechamento, dia_vencimento = int(dia_fechamento), int(dia_vencimento)
    if not 1 <= dia_fechamento <= 31 or not 1 <= dia_vencimento <= 31:
        raise ValueError("Os dias de fechamento e vencimento devem ficar entre 1 e 31.")
    regra = _normalizar_regra(regra_fechamento)
    with conectar() as conexao:
        if _nome_cartao_duplicado(conexao, nome, id_ignorar=id_cartao):
            raise ValueError("Já existe outro cartão cadastrado com esse nome.")
        cursor = conexao.execute(
            """UPDATE cartoes
               SET nome = ?, dia_fechamento = ?, dia_vencimento = ?, regra_fechamento = ?
               WHERE id = ?""",
            (nome, dia_fechamento, dia_vencimento, regra, id_cartao),
        )
        return cursor.rowcount > 0


def alterar_status_cartao(id_cartao, ativo):
    with conectar() as conexao:
        cursor = conexao.execute(
            "UPDATE cartoes SET ativo = ? WHERE id = ?",
            (1 if ativo else 0, id_cartao),
        )
        return cursor.rowcount > 0


def registrar_compra(cartao_id, descricao, data_compra, valor_total,
                     numero_parcelas=1, categoria=None, observacao=None):
    descricao = (descricao or "").strip()
    if not descricao:
        raise ValueError("Informe a descrição da compra.")
    data_compra = _data_iso(data_compra)
    valores = dividir_em_parcelas(valor_total, numero_parcelas)
    total_centavos = sum(valores)
    if categoria in ("", "Sem categoria", None):
        categoria = None
    elif not isinstance(categoria, str):
        raise ValueError("Categoria inválida.")
    observacao = (observacao or "").strip() or None

    with conectar() as conexao:
        cartao = _cartao(conexao, cartao_id, incluir_inativo=False)
        cursor = conexao.execute(
            """INSERT INTO compras_cartao
               (cartao_id, descricao, categoria, data_compra,
                valor_total_centavos, numero_parcelas, observacao)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (cartao_id, descricao, categoria, data_compra, total_centavos,
             len(valores), observacao),
        )
        id_compra = cursor.lastrowid
        _criar_parcelas(conexao, id_compra, cartao, data_compra, valores)
        return id_compra


def obter_compra(id_compra):
    with conectar() as conexao:
        return conexao.execute("""
            SELECT id, cartao_id, descricao, categoria, data_compra,
                   valor_total_centavos, numero_parcelas, observacao, ativa
            FROM compras_cartao WHERE id = ?
        """, (id_compra,)).fetchone()


def listar_compras(cartao_id=None, incluir_canceladas=True, limite=None):
    sql = """SELECT cp.id, cp.cartao_id, c.nome, cp.descricao, cp.categoria,
                    cp.data_compra, cp.valor_total_centavos, cp.numero_parcelas,
                    cp.observacao, cp.ativa,
                    COALESCE((SELECT SUM(p.valor_centavos)
                              FROM parcelas_cartao p
                              WHERE p.compra_id = cp.id AND p.ativa = 1), 0) AS total_parcelado,
                    cp.versao_atual
             FROM compras_cartao cp
             JOIN cartoes c ON c.id = cp.cartao_id"""
    filtros, parametros = [], []
    if cartao_id is not None:
        filtros.append("cp.cartao_id = ?")
        parametros.append(int(cartao_id))
    if not incluir_canceladas:
        filtros.append("cp.ativa = 1")
    if filtros:
        sql += " WHERE " + " AND ".join(filtros)
    sql += " ORDER BY cp.data_compra DESC, cp.id DESC"
    if limite is not None:
        sql += " LIMIT ?"
        parametros.append(int(limite))
    with conectar() as conexao:
        return conexao.execute(sql, parametros).fetchall()


def listar_parcelas_compra(id_compra):
    with conectar() as conexao:
        return conexao.execute("""
            SELECT p.id, p.numero_parcela, p.total_parcelas, p.valor_centavos,
                   f.ano, f.mes, f.data_fechamento, f.data_vencimento,
                   f.id AS fatura_id, p.ativa, p.motivo_cancelamento, p.versao
            FROM parcelas_cartao p
            JOIN faturas_cartao f ON f.id = p.fatura_id
            WHERE p.compra_id = ?
            ORDER BY f.ano, f.mes
        """, (id_compra,)).fetchall()


def listar_historico_compra(id_compra):
    with conectar() as conexao:
        return conexao.execute("""SELECT id, cartao_id, descricao, categoria,
            data_compra, valor_total_centavos, numero_parcelas, observacao,
            alterado_em, motivo_alteracao
            FROM compras_cartao_historico WHERE compra_id = ?
            ORDER BY id DESC""", (id_compra,)).fetchall()


def _compra_tem_fatura_com_pagamento(conexao, id_compra):
    return conexao.execute("""
        SELECT 1
        FROM parcelas_cartao p
        JOIN pagamentos_fatura pg ON pg.fatura_id = p.fatura_id
        WHERE p.compra_id = ? AND p.ativa = 1 AND pg.estornado = 0
        LIMIT 1
    """, (id_compra,)).fetchone() is not None


def editar_compra(id_compra, cartao_id, descricao, data_compra, valor_total,
                  numero_parcelas=1, categoria=None, observacao=None):
    descricao = (descricao or "").strip()
    if not descricao:
        raise ValueError("Informe a descrição da compra.")
    data_compra = _data_iso(data_compra)
    valores = dividir_em_parcelas(valor_total, numero_parcelas)
    categoria = None if categoria in ("", "Sem categoria", None) else categoria
    observacao = (observacao or "").strip() or None

    with conectar() as conexao:
        compra = conexao.execute(
            """SELECT cartao_id, descricao, categoria, data_compra,
                      valor_total_centavos, numero_parcelas, observacao, ativa, versao_atual
               FROM compras_cartao WHERE id = ?""",
            (id_compra,),
        ).fetchone()
        if not compra or compra[7] != 1:
            raise ValueError("A compra não foi encontrada ou já foi cancelada.")
        if _compra_tem_fatura_com_pagamento(conexao, id_compra):
            raise ValueError(
                "Esta compra participa de uma fatura que ainda possui pagamento ativo. "
                "Para preservar o histórico, não é possível alterá-la. Estorne o pagamento ou registre um crédito/estorno na fatura correspondente."
            )
        cartao = _cartao(conexao, cartao_id, incluir_inativo=False)
        nova_versao = int(compra[8]) + 1
        conexao.execute("""INSERT INTO compras_cartao_historico
            (compra_id, cartao_id, descricao, categoria, data_compra,
             valor_total_centavos, numero_parcelas, observacao, motivo_alteracao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (id_compra, *compra[:7], "Compra editada pelo usuário"))
        conexao.execute("""UPDATE parcelas_cartao
            SET ativa = 0, cancelada_em = datetime('now', 'localtime'),
                motivo_cancelamento = 'Parcelas substituídas por edição'
            WHERE compra_id = ? AND ativa = 1""", (id_compra,))
        conexao.execute("""UPDATE compras_cartao
                           SET cartao_id = ?, descricao = ?, categoria = ?, data_compra = ?,
                               valor_total_centavos = ?, numero_parcelas = ?, observacao = ?,
                               versao_atual = ?
                           WHERE id = ?""",
                        (cartao_id, descricao, categoria, data_compra, sum(valores),
                         len(valores), observacao, nova_versao, id_compra))
        _criar_parcelas(conexao, id_compra, cartao, data_compra, valores, nova_versao)
        _remover_faturas_vazias(conexao)
        return True


def cancelar_compra(id_compra):
    with conectar() as conexao:
        compra = conexao.execute(
            "SELECT ativa, versao_atual FROM compras_cartao WHERE id = ?", (id_compra,)
        ).fetchone()
        if not compra or compra[0] != 1:
            return False
        if _compra_tem_fatura_com_pagamento(conexao, id_compra):
            raise ValueError(
                "Esta compra está em uma fatura que já recebeu pagamento. "
                "Não é possível cancelá-la automaticamente; registre um crédito/estorno na fatura."
            )
        conexao.execute(
            "UPDATE compras_cartao SET ativa = 0 WHERE id = ?", (id_compra,)
        )
        conexao.execute("""UPDATE parcelas_cartao
            SET ativa = 0, cancelada_em = datetime('now', 'localtime'),
                motivo_cancelamento = 'Compra cancelada pelo usuário'
            WHERE compra_id = ? AND versao = ? AND ativa = 1""", (id_compra, compra[1]))
        _remover_faturas_vazias(conexao)
        return True


def restaurar_compra(id_compra):
    with conectar() as conexao:
        compra = conexao.execute("""SELECT cp.cartao_id, cp.ativa, cp.versao_atual,
            c.ativo FROM compras_cartao cp JOIN cartoes c ON c.id = cp.cartao_id
            WHERE cp.id = ?""", (id_compra,)).fetchone()
        if not compra or compra[1] != 0:
            return False
        if compra[3] != 1:
            raise ValueError("Reative o cartão antes de restaurar esta compra.")
        pagamento = conexao.execute("""SELECT 1 FROM parcelas_cartao p
            JOIN pagamentos_fatura pg ON pg.fatura_id = p.fatura_id
            WHERE p.compra_id = ? AND p.versao = ? AND pg.estornado = 0
            LIMIT 1""", (id_compra, compra[2])).fetchone()
        if pagamento:
            raise ValueError("Uma fatura ligada a esta compra recebeu pagamento. Não é possível restaurá-la automaticamente.")
        conexao.execute("UPDATE compras_cartao SET ativa = 1 WHERE id = ?", (id_compra,))
        conexao.execute("UPDATE parcelas_cartao SET ativa = 1, cancelada_em = NULL, motivo_cancelamento = NULL WHERE compra_id = ? AND versao = ?", (id_compra, compra[2]))
        return True


def _remover_faturas_vazias(conexao):
    conexao.execute("""
        DELETE FROM faturas_cartao
        WHERE NOT EXISTS (SELECT 1 FROM parcelas_cartao p WHERE p.fatura_id = faturas_cartao.id)
          AND NOT EXISTS (SELECT 1 FROM ajustes_fatura a WHERE a.fatura_id = faturas_cartao.id)
          AND NOT EXISTS (SELECT 1 FROM pagamentos_fatura pg WHERE pg.fatura_id = faturas_cartao.id)
          AND NOT EXISTS (SELECT 1 FROM faturas_antigas_importadas m WHERE m.id_fatura_nova = faturas_cartao.id)
    """)


def _consulta_faturas_sql():
    return """SELECT
        f.id, f.cartao_id, c.nome, f.ano, f.mes,
        f.data_fechamento, f.data_vencimento,
        COALESCE((SELECT SUM(p.valor_centavos)
                  FROM parcelas_cartao p
                  JOIN compras_cartao cp ON cp.id = p.compra_id
                  WHERE p.fatura_id = f.id AND p.ativa = 1 AND cp.ativa = 1), 0)
        + COALESCE((SELECT SUM(CASE WHEN a.tipo = 'Crédito' THEN -a.valor_centavos
                                    ELSE a.valor_centavos END)
                    FROM ajustes_fatura a WHERE a.fatura_id = f.id AND a.cancelado = 0), 0) AS total_centavos,
        COALESCE((SELECT SUM(pg.valor_centavos) FROM pagamentos_fatura pg
                  WHERE pg.fatura_id = f.id AND pg.estornado = 0), 0) AS pago_centavos
        FROM faturas_cartao f
        JOIN cartoes c ON c.id = f.cartao_id"""


def listar_faturas_mensais(cartao_id=None, ano=None, mes=None):
    sql = _consulta_faturas_sql()
    filtros, parametros = [], []
    if cartao_id is not None:
        filtros.append("f.cartao_id = ?")
        parametros.append(int(cartao_id))
    if ano is not None:
        filtros.append("f.ano = ?")
        parametros.append(int(ano))
    if mes is not None:
        filtros.append("f.mes = ?")
        parametros.append(int(mes))
    if filtros:
        sql += " WHERE " + " AND ".join(filtros)
    sql += " ORDER BY f.data_vencimento DESC, c.nome COLLATE NOCASE"
    with conectar() as conexao:
        return conexao.execute(sql, parametros).fetchall()


def obter_fatura_mensal(id_fatura):
    sql = _consulta_faturas_sql() + " WHERE f.id = ?"
    with conectar() as conexao:
        return conexao.execute(sql, (id_fatura,)).fetchone()


def editar_datas_fatura(id_fatura, data_fechamento, data_vencimento):
    data_fechamento = _data_iso(data_fechamento)
    data_vencimento = _data_iso(data_vencimento)
    if date.fromisoformat(data_vencimento) < date.fromisoformat(data_fechamento):
        raise ValueError("O vencimento não pode ser anterior ao fechamento.")
    with conectar() as conexao:
        cursor = conexao.execute("""UPDATE faturas_cartao
            SET data_fechamento = ?, data_vencimento = ?
            WHERE id = ?""", (data_fechamento, data_vencimento, id_fatura))
        return cursor.rowcount > 0


def listar_itens_fatura(id_fatura):
    with conectar() as conexao:
        parcelas = conexao.execute("""
            SELECT 'Parcela' AS tipo, cp.descricao, cp.categoria,
                   p.valor_centavos, p.numero_parcela, p.total_parcelas,
                   cp.id AS compra_id, p.id AS item_id, 1 AS ativo
            FROM parcelas_cartao p
            JOIN compras_cartao cp ON cp.id = p.compra_id
            WHERE p.fatura_id = ? AND p.ativa = 1 AND cp.ativa = 1
            ORDER BY cp.descricao COLLATE NOCASE
        """, (id_fatura,)).fetchall()
        ajustes = conexao.execute("""
            SELECT tipo, descricao, NULL AS categoria,
                   CASE WHEN tipo = 'Crédito' THEN -valor_centavos ELSE valor_centavos END,
                   NULL, NULL, NULL, id, CASE WHEN cancelado = 1 THEN 0 ELSE 1 END
            FROM ajustes_fatura
            WHERE fatura_id = ?
            ORDER BY id
        """, (id_fatura,)).fetchall()
        return parcelas + ajustes


def registrar_pagamento_fatura(id_fatura, valor, data_pagamento=None, observacao=None):
    valor_centavos = _centavos(valor)
    data_pagamento = _data_iso(data_pagamento or date.today())
    observacao = (observacao or "").strip() or None
    with conectar() as conexao:
        fatura = obter_fatura_mensal(id_fatura)
        if not fatura:
            raise ValueError("Fatura não encontrada.")
        total_centavos, pago_centavos = int(fatura[7]), int(fatura[8])
        saldo = max(total_centavos - pago_centavos, 0)
        if saldo <= 0:
            raise ValueError("Esta fatura não possui saldo a pagar.")
        if valor_centavos > saldo:
            raise ValueError("O pagamento não pode ser maior que o saldo restante.")
        cursor = conexao.execute("""INSERT INTO pagamentos_fatura
            (fatura_id, valor_centavos, data_pagamento, observacao)
            VALUES (?, ?, ?, ?)""",
            (id_fatura, valor_centavos, data_pagamento, observacao))
        return cursor.lastrowid


def listar_pagamentos_fatura(id_fatura):
    with conectar() as conexao:
        return conexao.execute("""SELECT id, valor_centavos, data_pagamento, observacao,
                                      estornado, motivo_estorno
            FROM pagamentos_fatura WHERE fatura_id = ?
            ORDER BY COALESCE(data_pagamento, criado_em), id""", (id_fatura,)).fetchall()


def estornar_pagamento_fatura(id_pagamento, motivo="Correção de lançamento"):
    motivo = (motivo or "Correção de lançamento").strip()
    with conectar() as conexao:
        cursor = conexao.execute("""UPDATE pagamentos_fatura
            SET estornado = 1, estornado_em = datetime('now', 'localtime'), motivo_estorno = ?
            WHERE id = ? AND estornado = 0""", (motivo, id_pagamento))
        return cursor.rowcount > 0


def excluir_pagamento_fatura(id_pagamento):
    """Compatibilidade: a remoção agora é um estorno lógico, nunca DELETE."""
    return estornar_pagamento_fatura(id_pagamento)


def adicionar_ajuste_fatura(id_fatura, tipo, descricao, valor):
    tipo = (tipo or "").strip().title()
    descricao = (descricao or "").strip()
    if tipo not in TIPOS_AJUSTE:
        raise ValueError("Selecione Encargo ou Crédito/Estorno.")
    if not descricao:
        raise ValueError("Informe a descrição do ajuste.")
    valor_centavos = _centavos(valor)
    with conectar() as conexao:
        if not conexao.execute("SELECT 1 FROM faturas_cartao WHERE id = ?", (id_fatura,)).fetchone():
            raise ValueError("Fatura não encontrada.")
        cursor = conexao.execute("""INSERT INTO ajustes_fatura
            (fatura_id, tipo, descricao, valor_centavos)
            VALUES (?, ?, ?, ?)""", (id_fatura, tipo, descricao, valor_centavos))
        return cursor.lastrowid


def estornar_ajuste_fatura(id_ajuste, motivo="Correção de lançamento"):
    motivo = (motivo or "Correção de lançamento").strip()
    with conectar() as conexao:
        cursor = conexao.execute("""UPDATE ajustes_fatura
            SET cancelado = 1, cancelado_em = datetime('now', 'localtime'), motivo_cancelamento = ?
            WHERE id = ? AND cancelado = 0 AND tipo <> 'Legado'""", (motivo, id_ajuste))
        return cursor.rowcount > 0


def excluir_ajuste_fatura(id_ajuste):
    """Compatibilidade: a remoção agora é um cancelamento lógico."""
    return estornar_ajuste_fatura(id_ajuste)


def registrar_ajuste_no_ciclo(cartao_id, ano, mes, tipo, descricao, valor):
    """Cria (se necessário) uma fatura mensal e inclui um encargo/crédito nela."""
    tipo = (tipo or "").strip().title()
    descricao = (descricao or "").strip()
    if tipo not in {"Encargo", "Crédito"}:
        raise ValueError("Selecione Encargo ou Crédito.")
    if not descricao:
        raise ValueError("Informe a descrição do ajuste.")
    valor_centavos = _centavos(valor)
    ano, mes = int(ano), int(mes)
    if not 1 <= mes <= 12:
        raise ValueError("Mês inválido.")

    with conectar() as conexao:
        cartao = _cartao(conexao, cartao_id, incluir_inativo=True)
        id_fatura = _garantir_fatura(conexao, cartao, ano, mes)
        cursor = conexao.execute("""INSERT INTO ajustes_fatura
            (fatura_id, tipo, descricao, valor_centavos)
            VALUES (?, ?, ?, ?)""", (id_fatura, tipo, descricao, valor_centavos))
        return id_fatura, cursor.lastrowid


def calcular_situacao_fatura(total_centavos, pago_centavos, vencimento, hoje=None):
    hoje = hoje or date.today()
    total_centavos, pago_centavos = int(total_centavos), int(pago_centavos)
    saldo = total_centavos - pago_centavos
    vencida = date.fromisoformat(vencimento) < hoje

    if saldo < 0:
        return "Crédito disponível", abs(saldo)
    if total_centavos == 0 and pago_centavos == 0:
        return "Sem saldo", 0
    if saldo == 0:
        return "Paga", 0
    if pago_centavos > 0 and vencida:
        return "Parcial atrasada", saldo
    if pago_centavos > 0:
        return "Parcial", saldo
    if vencida:
        return "Atrasada", saldo
    return "Pendente", saldo


def resumo_cartoes():
    hoje = date.today()
    faturas = listar_faturas_mensais()
    cartoes = listar_cartoes_credito(ativos=True)
    saldo_aberto = 0
    atrasadas = 0
    pagas = 0
    comprometido_futuro = 0
    for fatura in faturas:
        situacao, saldo = calcular_situacao_fatura(fatura[7], fatura[8], fatura[6], hoje)
        if situacao != "Crédito disponível":
            saldo_aberto += saldo
        if situacao in {"Atrasada", "Parcial atrasada"}:
            atrasadas += 1
        if situacao == "Paga":
            pagas += 1
        if situacao != "Crédito disponível" and date.fromisoformat(fatura[6]) >= hoje and saldo > 0:
            comprometido_futuro += saldo
    return {
        "cartoes_ativos": len(cartoes),
        "saldo_aberto_centavos": saldo_aberto,
        "faturas_atrasadas": atrasadas,
        "faturas_pagas": pagas,
        "comprometido_futuro_centavos": comprometido_futuro,
    }
