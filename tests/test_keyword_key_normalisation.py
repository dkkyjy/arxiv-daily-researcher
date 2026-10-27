import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.analysis_agent import (  # noqa: E402
    ScoreValidationError,
    _remap_keyword_scores,
)

EXPECTED = ["tidal disruption events", "high-energy neutrinos", "gamma-ray"]


class KeywordKeyNormalisationTests(unittest.TestCase):
    def test_acronym_expansion_maps_back_to_the_configured_key(self):
        mapped = _remap_keyword_scores(
            {
                "tidal disruption events (TDEs)": 8,
                "High-Energy Neutrinos": 6,
                "gamma-ray": 9,
            },
            EXPECTED,
        )
        self.assertEqual(
            mapped,
            {
                "tidal disruption events": 8,
                "high-energy neutrinos": 6,
                "gamma-ray": 9,
            },
        )

    def test_configured_key_with_a_parenthetical_still_matches_plain_output(self):
        mapped = _remap_keyword_scores(
            {"tidal disruption events": 4},
            ["tidal disruption events (TDEs)"],
        )
        self.assertEqual(mapped, {"tidal disruption events (TDEs)": 4})

    def test_unknown_keys_survive_so_the_caller_can_still_reject_them(self):
        self.assertEqual(
            _remap_keyword_scores({"unrelated topic": 5}, EXPECTED),
            {"unrelated topic": 5},
        )

    def test_exact_keys_are_untouched(self):
        raw = {"gamma-ray": 7}
        self.assertIs(_remap_keyword_scores(raw, EXPECTED)["gamma-ray"], raw["gamma-ray"])


if __name__ == "__main__":
    unittest.main()
