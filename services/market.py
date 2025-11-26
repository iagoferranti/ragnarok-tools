# services/market.py
import pandas as pd


def status_from_variation(variacao: float) -> str:
    """
    Regra de decisão baseada na variação %:
    - <= -5%  → Comprar
    - >= +10% → Vender
    - Caso contrário → Neutro
    """
    if variacao <= -0.05:
        return "Comprar"
    elif variacao >= 0.10:
        return "Vender"
    else:
        return "Neutro"


def compute_summary(df_prices: pd.DataFrame) -> pd.DataFrame:
    """
    Gera um resumo do mercado a partir de um DataFrame de preços.

    df_prices deve ter colunas:
      - item_id
      - item
      - date
      - price_zeny
    """
    if df_prices.empty:
        return pd.DataFrame()

    df = df_prices.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["item_id", "date"])

    summaries = []

    for item_id, group in df.groupby("item_id"):
        group = group.sort_values("date")
        last_row = group.iloc[-1]

        last_prices = group["price_zeny"].tail(5)
        media5 = last_prices.mean()
        last_price = last_row["price_zeny"]

        if media5 > 0:
            variacao = last_price / media5 - 1
        else:
            variacao = 0.0

        status = status_from_variation(variacao)

        summaries.append(
            {
                "Item": last_row["item"],
                "Última data": last_row["date"].date(),
                "Último preço (zeny)": last_price,
                "Média últimos 5": media5,
                "Variação % vs média 5": variacao,
                "Status": status,
            }
        )

    df_sum = pd.DataFrame(summaries).sort_values("Item")
    return df_sum
