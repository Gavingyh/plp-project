"""compare_taxonomies must measure the taxonomy the pipeline actually uses."""

import yaml

import aspects.compare_taxonomies as ct


def test_candidate_a_is_the_live_config():
    with open(ct.CONFIG_PATH) as f:
        live = yaml.safe_load(f)["aspects"]
    a = ct.candidates()["A_current_config"]
    assert set(a) == set(live) - {"other"}
    assert all(a[k] == live[k]["seed_terms"] for k in a)


def test_the_proposal_four_are_kept_separately():
    assert set(ct.candidates()["P_proposal_four"]) == {
        "dividend_policy", "asset_quality", "net_interest_margin", "management_guidance"}
