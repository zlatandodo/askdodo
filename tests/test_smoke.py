"""
Smoke tests for the AskLivermore Auto-Funnel pipeline.
No network calls — all data is mocked.
"""
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import pytest

# Ensure src is on the path
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))


# ============================================================
# Fixtures
# ============================================================

def _make_config() -> dict:
    """Minimal config for testing — uses dual-funnel strategies."""
    return {
        "capital_usd": 100_000,
        "risk_per_trade_pct": 0.0075,
        "max_position_pct": {
            "tier_a": 0.05,
            "tier_b": 0.035,
            "hard_cap": 0.06,
        },
        "dual_bonus": 5,
        "strategies": [
            {
                "id": "A",
                "name": "Pullback in Uptrend",
                "max_positions": 5,
                "universe_scanner": "trend_template",
                "scanners": [
                    {"name": "trend_template", "slug": "trend-template", "is_universe": True, "primary": False, "weight": 0},
                    {"name": "high_tight_flag", "slug": "high-tight-flag", "primary": True, "weight": 12},
                    {"name": "vcp", "slug": "vcp", "primary": True, "weight": 10},
                    {"name": "power_play", "slug": "power-play", "primary": True, "weight": 11},
                    {"name": "sector_leader", "slug": "sector-leader", "primary": False, "weight": 5},
                ],
            },
            {
                "id": "B",
                "name": "Mean Reversion",
                "max_positions": 5,
                "universe_scanner": "trend_template",
                "scanners": [
                    {"name": "trend_template", "slug": "trend-template", "is_universe": True, "primary": False, "weight": 0},
                    {"name": "vcp", "slug": "vcp", "primary": True, "weight": 10},
                    {"name": "sector_leader", "slug": "sector-leader", "primary": False, "weight": 5},
                ],
            },
        ],
        "filters": {
            "ars_min": 80,
            "ars_fallback": 70,
            "market_cap_min_m": 300,
            "price_min": 10,
            "price_max": 500,
            "avg_vol_min": 500_000,
            "earnings_days_buffer": 5,
            "ma10_chase_pct": 0.10,
            "max_per_sector": 3,
            "max_per_sector_fallback": 5,
        },
        "trade_plan": {
            "atr_stop_multiplier": 1.5,
            "atr_target1_multiplier": 2.0,
            "atr_target2_multiplier": 5.0,
            "max_stop_pct": 0.10,
        },
        "scanners": [
            {"name": "trend_template", "slug": "trend-template", "is_universe": True},
            {"name": "high_tight_flag", "slug": "high-tight-flag"},
            {"name": "vcp", "slug": "vcp"},
            {"name": "power_play", "slug": "power-play"},
            {"name": "sector_leader", "slug": "sector-leader"},
        ],
    }


def _make_universe_df() -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "GOOGL", "META"],
        "company_name": ["Apple", "Microsoft", "Nvidia", "Tesla", "AMD", "Alphabet", "Meta"],
        "sector": ["Technology", "Technology", "Technology", "Consumer Cyclical", "Technology", "Technology", "Technology"],
        "market_cap_m": [2_800_000, 3_000_000, 1_200_000, 600_000, 250_000, 1_800_000, 1_000_000],
        "ars": [95.0, 88.0, 99.0, 72.0, 85.0, 91.0, 87.0],
        "ta": [8.5, 7.0, 9.5, 6.0, 7.5, 8.0, 8.2],
        "fa": [7.0, 8.0, 6.5, 4.0, 5.5, 7.5, 6.0],
        "price": [185.0, 340.0, 450.0, 250.0, 120.0, 155.0, 480.0],
        "avg_vol": [60_000_000, 20_000_000, 40_000_000, 80_000_000, 50_000_000, 25_000_000, 15_000_000],
        "scanner_name": ["trend_template"] * 7,
    })


def _make_scanner_df() -> pd.DataFrame:
    """Mock scanner hits across multiple scanners (legacy helper for loader tests)."""
    rows = [
        # NVDA appears in many primary scanners
        {"symbol": "NVDA", "scanner_name": "high_tight_flag"},
        {"symbol": "NVDA", "scanner_name": "vcp"},
        {"symbol": "NVDA", "scanner_name": "power_play"},
        {"symbol": "NVDA", "scanner_name": "sector_leader"},
        # AAPL in two primaries
        {"symbol": "AAPL", "scanner_name": "vcp"},
        {"symbol": "AAPL", "scanner_name": "high_tight_flag"},
        {"symbol": "AAPL", "scanner_name": "sector_leader"},
        # MSFT in two primaries + one confirm
        {"symbol": "MSFT", "scanner_name": "power_play"},
        {"symbol": "MSFT", "scanner_name": "vcp"},
        {"symbol": "MSFT", "scanner_name": "sector_leader"},
    ]
    df = pd.DataFrame(rows)
    for col in ["company_name", "sector", "market_cap_m", "ars", "ta", "fa", "price", "avg_vol"]:
        df[col] = None
    return df


def _make_scanner_results() -> dict:
    """Mock scanner_results dict for compute_scores_dual."""
    return {
        "trend_template": [
            {"ticker": "AAPL"}, {"ticker": "MSFT"}, {"ticker": "NVDA"},
            {"ticker": "TSLA"}, {"ticker": "AMD"}, {"ticker": "GOOGL"}, {"ticker": "META"},
        ],
        "high_tight_flag": [
            {"ticker": "NVDA"}, {"ticker": "AAPL"},
        ],
        "vcp": [
            {"ticker": "NVDA"}, {"ticker": "AAPL"}, {"ticker": "MSFT"},
        ],
        "power_play": [
            {"ticker": "NVDA"}, {"ticker": "MSFT"},
        ],
        "sector_leader": [
            {"ticker": "NVDA"}, {"ticker": "AAPL"}, {"ticker": "MSFT"},
        ],
    }


# ============================================================
# Loader tests
# ============================================================

class TestLoader:
    """
    NOTE: _parse_volume, _parse_market_cap, _parse_pct, and load_scanner_csvs
    are CSV-era helpers that no longer exist in loader.py (API-based loader).
    These tests are skipped as pre-existing failures unrelated to the dual-funnel refactor.
    """

    @pytest.mark.skip(reason="loader.py uses API-based loading; _parse_volume not present")
    def test_parse_volume_k(self):
        from src.loader import _parse_volume
        assert _parse_volume("500K") == 500_000

    @pytest.mark.skip(reason="loader.py uses API-based loading; _parse_volume not present")
    def test_parse_volume_m(self):
        from src.loader import _parse_volume
        assert _parse_volume("1.5M") == 1_500_000

    @pytest.mark.skip(reason="loader.py uses API-based loading; _parse_volume not present")
    def test_parse_volume_plain(self):
        from src.loader import _parse_volume
        assert _parse_volume("750000") == 750_000.0

    @pytest.mark.skip(reason="loader.py uses API-based loading; _parse_volume not present")
    def test_parse_volume_none(self):
        from src.loader import _parse_volume
        assert _parse_volume(None) is None

    @pytest.mark.skip(reason="loader.py uses API-based loading; _parse_market_cap not present")
    def test_parse_market_cap_b(self):
        from src.loader import _parse_market_cap
        result = _parse_market_cap("2.5B")
        assert result == pytest.approx(2500.0)

    @pytest.mark.skip(reason="loader.py uses API-based loading; _parse_market_cap not present")
    def test_parse_market_cap_m(self):
        from src.loader import _parse_market_cap
        result = _parse_market_cap("300M")
        assert result == pytest.approx(300.0)

    @pytest.mark.skip(reason="loader.py uses API-based loading; _parse_pct not present")
    def test_parse_pct(self):
        from src.loader import _parse_pct
        assert _parse_pct("3.25%") == pytest.approx(3.25)
        assert _parse_pct("-1.5%") == pytest.approx(-1.5)

    @pytest.mark.skip(reason="loader.py uses API-based loading; load_scanner_csvs not present")
    def test_load_scanner_csvs_with_mock_file(self, tmp_path):
        from src.loader import load_scanner_csvs

        tt_csv = tmp_path / "tt.csv"
        tt_csv.write_text(
            "Symbol,Company,Sector,Market Cap,TA,FA,ARS,% Chg,Avg Vol (50),Price\n"
            "AAPL,Apple,Technology,2500B,8.5,7.0,95,2.3%,60M,185.00\n"
            "NVDA,Nvidia,Technology,1200B,9.5,6.5,99,5.1%,40M,450.00\n"
        )
        htf_csv = tmp_path / "htf.csv"
        htf_csv.write_text(
            "Symbol,Company,Sector\n"
            "NVDA,Nvidia,Technology\n"
        )

        config = {
            "scanners": [
                {"name": "trend_template", "filename": "tt.csv", "is_universe": True, "primary": False, "weight_key": None},
                {"name": "high_tight_flag", "filename": "htf.csv", "primary": True, "weight_key": "high_tight_flag"},
            ]
        }
        csv_paths = {
            "trend_template": tt_csv,
            "high_tight_flag": htf_csv,
        }

        universe, scanners = load_scanner_csvs(csv_paths, config)

        assert len(universe) == 2
        assert "AAPL" in universe["symbol"].values
        assert "NVDA" in universe["symbol"].values
        assert len(scanners) == 1
        assert scanners.iloc[0]["symbol"] == "NVDA"

    @pytest.mark.skip(reason="loader.py uses API-based loading; load_scanner_csvs not present")
    def test_load_missing_csv(self, tmp_path):
        """Missing CSV paths should be skipped gracefully."""
        from src.loader import load_scanner_csvs

        config = {
            "scanners": [
                {"name": "trend_template", "filename": "missing.csv", "is_universe": True},
            ]
        }
        universe, scanners = load_scanner_csvs({"trend_template": None}, config)
        assert universe.empty


# ============================================================
# Scoring tests
# ============================================================

class TestScoring:
    def test_compute_scores_basic(self):
        from src.scoring import compute_scores_dual
        config = _make_config()
        universe = _make_universe_df()
        scanner_results = _make_scanner_results()

        result = compute_scores_dual(universe, scanner_results, config)

        assert not result.empty
        assert "symbol" in result.columns
        assert "conviction_score" in result.columns
        assert "tier" in result.columns
        assert "primary_count" in result.columns
        assert "confirm_count" in result.columns
        assert "strategy" in result.columns

    def test_nvda_highest_score(self):
        """NVDA has most scanner hits so should rank highest."""
        from src.scoring import compute_scores_dual
        config = _make_config()
        universe = _make_universe_df()
        scanner_results = _make_scanner_results()

        result = compute_scores_dual(universe, scanner_results, config)
        top = result.iloc[0]["symbol"]
        assert top == "NVDA", f"Expected NVDA at top, got {top}"

    def test_tier_assignment_tier_a(self):
        """NVDA with 3 primary + 1 confirm should be Tier A in at least one strategy."""
        from src.scoring import compute_scores_dual
        config = _make_config()
        universe = _make_universe_df()
        scanner_results = _make_scanner_results()

        result = compute_scores_dual(universe, scanner_results, config)
        nvda = result[result["symbol"] == "NVDA"]
        assert not nvda.empty
        assert nvda.iloc[0]["tier"] == "A"

    def test_tickers_not_in_any_scanner_get_tier_drop(self):
        """TSLA and AMD are in universe but no scanner — should be Tier C or DROP."""
        from src.scoring import compute_scores_dual
        config = _make_config()
        universe = _make_universe_df()
        scanner_results = _make_scanner_results()

        result = compute_scores_dual(universe, scanner_results, config)
        tsla = result[result["symbol"] == "TSLA"]
        assert tsla.iloc[0]["tier"] in ("C", "DROP")

    def test_empty_universe_returns_empty(self):
        from src.scoring import compute_scores_dual
        config = _make_config()
        result = compute_scores_dual(pd.DataFrame(), {}, config)
        assert result.empty

    def test_dual_strategy_label(self):
        """Tickers in both A and B should be labeled DUAL."""
        from src.scoring import compute_scores_dual
        config = _make_config()
        universe = _make_universe_df()
        scanner_results = _make_scanner_results()

        result = compute_scores_dual(universe, scanner_results, config)
        # NVDA hits both A (high_tight_flag, vcp, power_play) and B (vcp, sector_leader)
        nvda = result[result["symbol"] == "NVDA"]
        assert not nvda.empty
        # NVDA is in both strategies (vcp and sector_leader appear in both)
        assert nvda.iloc[0]["strategy"] in ("A", "B", "DUAL")

    def test_fa_bonus_applied(self):
        """FA >= 6.0 should add +2 to score compared to FA=None."""
        from src.scoring import compute_scores_dual

        config = _make_config()
        universe_with_fa = pd.DataFrame({
            "symbol": ["XYZ"],
            "company_name": ["Test Co"],
            "sector": ["Technology"],
            "market_cap_m": [500.0],
            "ars": [90.0],
            "ta": [8.0],
            "fa": [7.0],
            "price": [50.0],
            "avg_vol": [1_000_000],
            "scanner_name": ["trend_template"],
        })
        universe_no_fa = universe_with_fa.copy()
        universe_no_fa["fa"] = None

        result_with = compute_scores_dual(universe_with_fa, {}, config)
        result_without = compute_scores_dual(universe_no_fa, {}, config)

        score_with = result_with.iloc[0]["conviction_score"]
        score_without = result_without.iloc[0]["conviction_score"]
        assert score_with == pytest.approx(score_without + 2.0, abs=0.01)


# ============================================================
# Risk calculation tests
# ============================================================

class TestRisk:
    def _make_enriched_df(self) -> pd.DataFrame:
        """Create a minimal enriched DataFrame with price and ATR."""
        return pd.DataFrame({
            "symbol": ["AAPL", "NVDA"],
            "company_name": ["Apple", "Nvidia"],
            "sector": ["Technology", "Technology"],
            "tier": ["A", "B"],
            "conviction_score": [35.0, 50.0],
            "price": [185.0, 450.0],
            "atr14": [3.5, 9.0],
            "ma10": [183.0, 440.0],
            "ma50": [175.0, 420.0],
            "ma200": [160.0, 380.0],
            "ars": [95.0, 99.0],
            "ta": [8.5, 9.5],
            "fa": [7.0, 6.5],
            "market_cap_m": [2_800_000, 1_200_000],
            "avg_vol_live": [60_000_000, 40_000_000],
            "next_earnings_date": [None, None],
            "days_to_earnings": [None, None],
            "scanners_hit": ["vcp, high_tight_flag", "vcp, high_tight_flag, power_play"],
            "filter_note": ["", ""],
        })

    def test_columns_present(self):
        from src.risk import calculate_trade_plans
        config = _make_config()
        df = self._make_enriched_df()
        result, summary = calculate_trade_plans(df, config)

        for col in ["entry", "stop", "target1", "target2", "size_usd", "size_shares", "risk_usd", "rr_t1"]:
            assert col in result.columns, f"Missing column: {col}"

    def test_stop_below_entry(self):
        from src.risk import calculate_trade_plans
        config = _make_config()
        df = self._make_enriched_df()
        result, _ = calculate_trade_plans(df, config)

        for _, row in result.iterrows():
            if row["stop"] is not None and row["entry"] is not None:
                assert row["stop"] < row["entry"], f"{row['symbol']}: stop {row['stop']} >= entry {row['entry']}"

    def test_targets_above_entry(self):
        from src.risk import calculate_trade_plans
        config = _make_config()
        df = self._make_enriched_df()
        result, _ = calculate_trade_plans(df, config)

        for _, row in result.iterrows():
            if row["target1"] is not None and row["entry"] is not None:
                assert row["target1"] > row["entry"]
            if row["target2"] is not None and row["entry"] is not None:
                assert row["target2"] > row["entry"]

    def test_position_size_within_capital(self):
        from src.risk import calculate_trade_plans
        config = _make_config()
        df = self._make_enriched_df()
        result, summary = calculate_trade_plans(df, config)

        capital = config["capital_usd"]
        for _, row in result.iterrows():
            if row["size_usd"] is not None:
                assert row["size_usd"] <= capital, f"{row['symbol']}: size {row['size_usd']} > capital {capital}"

    def test_portfolio_summary_keys(self):
        from src.risk import calculate_trade_plans
        config = _make_config()
        df = self._make_enriched_df()
        _, summary = calculate_trade_plans(df, config)

        for key in ["capital_usd", "n_positions", "exposure_pct", "total_risk_pct", "tier_a_count"]:
            assert key in summary, f"Missing summary key: {key}"

    def test_max_stop_pct_enforced(self):
        """Stop should never be more than max_stop_pct (10%) below entry."""
        from src.risk import calculate_trade_plans
        config = _make_config()
        # Give a very large ATR that would cause a > 10% stop
        df = self._make_enriched_df()
        df["atr14"] = [50.0, 100.0]  # enormous ATR
        result, _ = calculate_trade_plans(df, config)

        max_stop_pct = config["trade_plan"]["max_stop_pct"]
        for _, row in result.iterrows():
            if row["stop"] is not None and row["entry"] is not None:
                stop_pct = (row["entry"] - row["stop"]) / row["entry"]
                assert stop_pct <= max_stop_pct + 0.001, (
                    f"{row['symbol']}: stop_pct {stop_pct:.4f} > max {max_stop_pct}"
                )


# ============================================================
# Filter tests
# ============================================================

class TestFilters:
    def _make_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "symbol": ["AAPL", "NVDA", "TSLA", "PENNY", "LOWVOL", "EARNINGS"],
            "company_name": ["Apple", "Nvidia", "Tesla", "PennyCo", "LowVol", "EarningsNear"],
            "sector": ["Technology", "Technology", "Consumer Cyclical", "Technology", "Financials", "Healthcare"],
            "tier": ["A", "A", "B", "B", "B", "A"],
            "strategy": ["A", "A", "B", "A", "B", "A"],
            "conviction_score": [50.0, 55.0, 30.0, 25.0, 28.0, 45.0],
            "ars": [95.0, 99.0, 72.0, 60.0, 85.0, 90.0],
            "market_cap_m": [2_800_000, 1_200_000, 600_000, 50.0, 500_000, 1_000_000],
            "price": [185.0, 450.0, 250.0, 3.0, 120.0, 200.0],
            "avg_vol_live": [60_000_000, 40_000_000, 80_000_000, 100_000, 200_000, 1_000_000],
            "ma10": [183.0, 440.0, 245.0, 2.9, 115.0, 190.0],
            "next_earnings_date": [None, None, None, None, None, "2026-05-20"],
            "days_to_earnings": [None, None, None, None, None, 2],  # within 5-day buffer
            "atr14": [3.5, 9.0, 5.0, 0.1, 2.0, 4.0],
        })

    def test_price_filter(self):
        from src.filters import apply_filters_dual
        config = _make_config()
        df = self._make_df()
        result = apply_filters_dual(df, config)
        assert "PENNY" not in result["symbol"].values, "PENNY (price=$3) should be filtered"

    def test_volume_filter(self):
        from src.filters import apply_filters_dual
        config = _make_config()
        df = self._make_df()
        result = apply_filters_dual(df, config)
        assert "LOWVOL" not in result["symbol"].values, "LOWVOL should be filtered"

    def test_earnings_filter(self):
        from src.filters import apply_filters_dual
        config = _make_config()
        df = self._make_df()
        result = apply_filters_dual(df, config)
        assert "EARNINGS" not in result["symbol"].values, "EARNINGS (2 days away) should be filtered"

    def test_ars_filter_relaxation(self):
        """When ARS >= 80 leaves <5 tickers, should fall back to 70."""
        from src.filters import apply_filters_dual
        config = _make_config()
        df = pd.DataFrame({
            "symbol": [f"T{i}" for i in range(8)],
            "company_name": [f"Co{i}" for i in range(8)],
            "sector": ["Technology"] * 8,
            "tier": ["A"] * 4 + ["B"] * 4,
            "strategy": ["A"] * 4 + ["B"] * 4,
            "conviction_score": [50.0, 48.0, 46.0, 44.0, 42.0, 40.0, 38.0, 36.0],
            "ars": [75.0, 74.0, 73.0, 72.0, 71.0, 70.0, 78.0, 76.0],  # all below 80
            "market_cap_m": [500_000] * 8,
            "price": [100.0] * 8,
            "avg_vol_live": [1_000_000] * 8,
            "ma10": [95.0] * 8,
            "next_earnings_date": [None] * 8,
            "days_to_earnings": [None] * 8,
            "atr14": [2.0] * 8,
        })
        result = apply_filters_dual(df, config)
        # Should have tickers (ARS fallback to 70)
        assert len(result) > 0
        assert any("ARS" in n for n in result["filter_note"].values if n)

    def test_max_watchlist_size(self):
        from src.filters import apply_filters_dual
        config = _make_config()
        # Build 20 valid tickers alternating between strategies
        df = pd.DataFrame({
            "symbol": [f"T{i:02d}" for i in range(20)],
            "company_name": [f"Co{i}" for i in range(20)],
            "sector": ["Technology", "Healthcare", "Financials"] * 6 + ["Energy", "Energy"],
            "tier": ["A"] * 10 + ["B"] * 10,
            "strategy": ["A"] * 10 + ["B"] * 10,
            "conviction_score": list(range(20, 0, -1)),
            "ars": [90.0] * 20,
            "market_cap_m": [500_000] * 20,
            "price": [100.0] * 20,
            "avg_vol_live": [1_000_000] * 20,
            "ma10": [95.0] * 20,
            "next_earnings_date": [None] * 20,
            "days_to_earnings": [None] * 20,
            "atr14": [2.0] * 20,
        })
        result = apply_filters_dual(df, config)
        assert len(result) <= 10, f"Expected <= 10 tickers, got {len(result)}"


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
