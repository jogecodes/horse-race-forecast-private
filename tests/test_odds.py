import pytest
from horse_racing.odds import decimal,classify,odds_db,add


def test_prices_are_not_negative_or_imputed():
    assert decimal('3,9')==3.9
    assert decimal('SP') is None and decimal('0.5') is None and decimal('nan') is None


def test_scheduled_time_is_not_actual_off_proof():
    quote='2026-04-16T11:44:00Z';scheduled='2026-04-16T11:45:00Z'
    assert classify(quote,scheduled)=='before_scheduled_start_only'
    assert classify('2026-04-16T11:46:00Z',scheduled)=='at_or_after_scheduled_start'
    assert classify(quote,scheduled,scheduled,preplay=False)!='provider_timestamped_before_actual_start'
    assert classify(quote,scheduled,scheduled,preplay=True)=='provider_timestamped_before_actual_start'
    assert classify(None,None)=='time_unverified'
