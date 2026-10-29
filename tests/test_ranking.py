from georesponse.ranking import access_factor, coverage_plan, rank_disclosure, rank_sites


def test_false_positive_ranks_first_then_reorders(scenario):
    sites = scenario["sites"]
    ranked, _ = rank_sites(sites)
    assert ranked[0].site["id"] == "S01"
    after, _ = rank_sites(sites, exclude={"S01"})
    assert after[0].site["id"] == "S02"
    assert all(item.site["id"] != "S01" for item in after)


def test_contributions_sum_to_score(scenario):
    ranked, warnings = rank_sites(scenario["sites"])
    for item in ranked:
        assert abs(sum(item.contributions.values()) - item.score) < 1e-9
    assert isinstance(warnings, list)


def test_coverage_plan_respects_team_count(scenario):
    ranked, _ = rank_sites(scenario["sites"])
    plan = coverage_plan(ranked, 3)
    assert len(plan) == 3
    assert len({p["team"] for p in plan}) == 3
    assert len({p["siteId"] for p in plan}) == 3


def test_access_factor_orders_risk():
    assert access_factor("blocked") > access_factor("flooded") > access_factor("clear")
    assert access_factor("unknown") == 0.5


def test_rank_disclosure_matches_rank(scenario):
    ranked, _ = rank_sites(scenario["sites"])
    disclosure = rank_disclosure(ranked)
    assert len(disclosure) == len(ranked)
    assert disclosure[0]["rank"] == 1
    assert "contributions" in disclosure[0]


def test_weights_are_normalised(scenario):
    ranked, _ = rank_sites(scenario["sites"], weights={"extent": 1, "confidence": 0, "value": 0, "access": 0, "population": 0})
    assert ranked[0].site["id"] == "S01"
    assert abs(ranked[0].score - ranked[0].contributions["extent"]) < 1e-9
