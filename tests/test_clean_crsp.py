from pathlib import Path


def test_cleaner_is_scoped_to_raw_and_processed_paths():
    source = (Path(__file__).parents[1] / "src" / "data" / "clean_crsp.py").read_text()
    assert 'RAW = ROOT / "crsp" / "yb8xejbnpiflaprb.csv"' in source
    assert 'OUT = ROOT / "data" / "processed"' in source
    assert 'SecInfoStartDt' in source and 'SecInfoEndDt' in source
