def formatar_moeda(valor):
    """Formata um valor numérico no padrão brasileiro de moeda."""
    valor_formatado = f"R$ {valor:,.2f}"
    return (
        valor_formatado
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )
