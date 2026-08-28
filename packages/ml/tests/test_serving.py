from fplguru_ml.features import FEATURE_NAMES_ADV
from fplguru_ml.serving import adv_feature_row

APP = {"total_points": 6, "minutes": 90, "goals": 1, "assists": 0}


def test_adv_feature_row_none_when_history_thin():
    assert adv_feature_row([APP, APP], was_home=True, value=100,
                           opp_conceded_to_pos_5=3.0) is None


def test_adv_feature_row_has_all_14_features_with_zero_xg():
    row = adv_feature_row([APP, APP, APP], was_home=True, value=100,
                          opp_conceded_to_pos_5=3.0)
    assert row is not None
    assert set(FEATURE_NAMES_ADV) <= set(row)
    for k in ("form_xg_5", "form_xa_5", "xg_overperf_5", "form_xgc_5", "form_ict_5"):
        assert row[k] == 0.0
    assert row["was_home"] == 1.0
