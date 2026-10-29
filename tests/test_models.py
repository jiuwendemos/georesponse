from georesponse.models import FEATURES, default_classifier, model_card, score_site, train_demo_model


def test_synthetic_fit_beats_chance():
    model = train_demo_model()
    assert model.metrics["precision"] >= 0.7
    assert model.metrics["recall"] >= 0.7
    assert model.metrics["f1"] >= 0.7


def test_save_and_load(tmp_path):
    model = train_demo_model()
    path = tmp_path / "model.json"
    model.save(path)
    loaded = __import__("georesponse.models", fromlist=["DamageClassifier"]).DamageClassifier.load(path)
    row = {name: 0.5 for name in FEATURES}
    assert abs(loaded.predict_proba([row])[0] - model.predict_proba([row])[0]) < 1e-9


def test_score_site_and_card():
    model = default_classifier()
    high = score_site({"changeExtentM2": 11000, "confidence": 0.95, "valueEur": 5_000_000, "population": 1500, "accessStatus": "blocked"}, model)
    low = score_site({"changeExtentM2": 500, "confidence": 0.55, "valueEur": 100_000, "population": 40, "accessStatus": "clear"}, model)
    assert high > low
    card = model_card()
    assert card["trainedRows"] > 0
    assert card["metrics"]["precision"] > 0.6
