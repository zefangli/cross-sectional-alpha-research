from datetime import date, timedelta

import duckdb

from src.data.build_research_panel import build_panel


def rows(n, missing=None, final_delisting_return=None):
    missing = set(missing or [])
    result = []
    for i in range(n):
        ret = None if i in missing else 0.01
        flag = 'N'
        if final_delisting_return is not None and i == n - 1:
            ret, flag = final_delisting_return, 'Y'
        result.append((
            1, date(2020, 1, 1) + timedelta(days=i), ret, 10.0, 1_000_000,
            100.0, 10_000.0, 0.0, ret, 'Y', 'EQTY', 'COM', 'NS', 'N',
            'CORP', 'RW', 'A', flag, 'NA', 'D3',
        ))
    return result


def panel(rows_to_insert):
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE source_data (
            permno BIGINT, date DATE, ret DOUBLE, price DOUBLE, volume BIGINT,
            market_cap DOUBLE, shares_outstanding DOUBLE, value_weighted_market_return DOUBLE,
            return_ex_dividends DOUBLE, us_incorporated_flag VARCHAR, security_type VARCHAR,
            security_subtype VARCHAR, share_type VARCHAR, primary_exchange VARCHAR,
            issuer_type VARCHAR, conditional_type VARCHAR, trading_status_flag VARCHAR,
            delisting_flag VARCHAR, return_missing_flag VARCHAR, return_duration_flag VARCHAR
        )
    """)
    con.executemany("INSERT INTO source_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows_to_insert)
    return build_panel(con, "source_data").df()


def test_eligibility_does_not_use_future_rows():
    baseline = panel(rows(300))
    changed = rows(300)
    changed[280] = (*changed[280][:3], 1.0, 0, *changed[280][5:])
    future_changed = panel(changed)
    target_date = baseline.iloc[270].date
    assert baseline.loc[baseline.date == target_date, 'eligibility_flag'].item()
    assert baseline.loc[baseline.date == target_date, 'eligibility_flag'].item() == future_changed.loc[future_changed.date == target_date, 'eligibility_flag'].item()


def test_forward_return_uses_the_next_twenty_returns():
    result = panel(rows(30))
    expected = 1.01 ** 20 - 1
    assert abs(result.iloc[0].forward_return_20d - expected) < 1e-12
    assert result.iloc[10].forward_return_20d != result.iloc[10].forward_return_20d


def test_missing_and_final_delisting_return_behavior():
    missing_result = panel(rows(30, missing={5}))
    assert missing_result.iloc[0].forward_return_20d != missing_result.iloc[0].forward_return_20d

    gapped = rows(30)
    del gapped[5]
    gapped += [tuple([2, *row[1:]]) for row in rows(30)]
    gapped_result = panel(gapped)
    first_gapped = gapped_result[gapped_result.permno == 1].iloc[0].forward_return_20d
    assert first_gapped != first_gapped

    delisting_result = panel(rows(21, final_delisting_return=-0.5))
    assert abs(delisting_result.iloc[0].forward_return_20d - ((1.01 ** 19) * 0.5 - 1)) < 1e-12
    assert delisting_result.iloc[-1].forward_return_20d != delisting_result.iloc[-1].forward_return_20d
