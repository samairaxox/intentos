from app.finance.benchmark import run_benchmark


def test_reproducible_financial_benchmark():
    result=run_benchmark()
    assert result['summary']['cases']==18
    assert result['summary']['strategy_comparisons']==54
    assert result['summary']['hard_constraint_violations']==0
    assert result['summary']['consistent_repeats']==18
    assert result['summary']['price_increase_replans_feasible']==18
