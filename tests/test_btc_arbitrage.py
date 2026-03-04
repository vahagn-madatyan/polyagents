import pytest

from agents.application.btc_arbitrage import compute_model_probability


class TestComputeModelProbability:
    def test_price_well_above_target_up_momentum(self):
        prob = compute_model_probability(
            current_price=98000.0,
            target_price=97000.0,
            direction="above",
            momentum_1m=0.001,
            momentum_5m=0.005,
            time_remaining_secs=300,
        )
        assert prob > 0.7  # high confidence target is met

    def test_price_well_below_target_down_momentum(self):
        prob = compute_model_probability(
            current_price=96000.0,
            target_price=97000.0,
            direction="above",
            momentum_1m=-0.001,
            momentum_5m=-0.005,
            time_remaining_secs=300,
        )
        assert prob < 0.3  # low confidence target is met

    def test_price_at_target_no_momentum(self):
        prob = compute_model_probability(
            current_price=97000.0,
            target_price=97000.0,
            direction="above",
            momentum_1m=0.0,
            momentum_5m=0.0,
            time_remaining_secs=300,
        )
        assert 0.3 < prob < 0.7  # uncertain

    def test_probability_clamped(self):
        prob = compute_model_probability(
            current_price=200000.0,
            target_price=97000.0,
            direction="above",
            momentum_1m=0.05,
            momentum_5m=0.10,
            time_remaining_secs=300,
        )
        assert 0.01 <= prob <= 0.99
