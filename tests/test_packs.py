from georesponse.packs import all_packs, build_pack, government_framework, partner_programme


def test_sector_packs():
    packs = all_packs()
    assert {p["id"] for p in packs} == {"agriculture", "mining"}
    agriculture = build_pack("agriculture")
    assert any("NDVI" in item for item in agriculture["changeTypes"])
    assert agriculture["guardrails"]


def test_government_and_partner():
    gov = government_framework()
    assert "Human review" in gov["obligations"][0]
    partner = partner_programme()
    assert any("Reinsurers" in p for p in partner["partners"])
