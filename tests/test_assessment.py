from georesponse.assessment import one_paragraph, write_assessment
from georesponse.ranking import rank_sites


def test_assessment_writer_discloses_numbers_and_human_review(scenario):
    ranked, _ = rank_sites(scenario["sites"])
    assessment = write_assessment(scenario, ranked)
    assert "priority sites" in assessment["summary"]
    assert assessment["modelVersion"]
    assert assessment["findings"]
    assert any("human" in item.lower() for item in assessment["limitations"])
    assert assessment["disclosure"].startswith("AI-assisted")
    assert assessment["claim"]["adjusterRequired"] is True
    assert assessment["trace"]


def test_rejected_finding_is_counted_and_removed(scenario):
    ranked, _ = rank_sites(scenario["sites"], exclude={"S01"})
    assessment = write_assessment(scenario, ranked, reviews={"S01": "rejected"})
    assert assessment["metrics"]["rejected"] == 1
    assert all(finding["id"] != "S01" for finding in assessment["findings"])
    assert "rejected" in assessment["summary"]


def test_one_paragraph_names_top_site(scenario):
    ranked, _ = rank_sites(scenario["sites"])
    paragraph = one_paragraph(scenario, ranked)
    assert ranked[0].site["name"] in paragraph
    assert "analyst signs" in paragraph


def test_confidence_label_thresholds(scenario):
    ranked, _ = rank_sites(scenario["sites"])
    assessment = write_assessment(scenario, ranked)
    labels = {finding["confidenceLabel"] for finding in assessment["findings"]}
    assert labels <= {"high", "medium", "low"}
