import pandas as pd

from src.evaluation.week5_lock import select


def candidates(rows):
    """rows: (book, net_sharpe_10bp, realised_beta) triples -- the only two
    columns `select` reads."""
    return pd.DataFrame(rows, columns=["book", "net_sharpe_10bp", "realised_beta"])


# --- select: winner is the max net Sharpe among only the passing rows -------

def test_select_picks_the_max_net_sharpe_among_rows_that_pass_the_beta_constraint():
    table = candidates([("a", 0.10, 0.05), ("b", 0.30, 0.05), ("c", 0.20, 0.03)])
    winner = select(table).iloc[0]
    assert winner.book == "b"


def test_a_candidate_that_violates_the_beta_constraint_never_wins_even_with_the_top_net_sharpe():
    table = candidates([("best_but_disqualified", 0.90, 0.25),
                         ("a", 0.10, 0.05), ("b", 0.05, -0.08)])
    winner = select(table).iloc[0]
    assert winner.book != "best_but_disqualified"
