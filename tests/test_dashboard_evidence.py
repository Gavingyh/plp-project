"""Loaded-evidence filters, paging and honest presentation of predictions."""

import pandas as pd

from dashboard.evidence import filter_examples
from dashboard.style import quote_card
from test_dashboard_views import DashboardAppTestCase, fake_api


def examples(count=25):
    return [
        dict(
            sentence_id=f"s{i}",
            text=f"Evidence sentence {i}.",
            source="earnings" if i % 2 == 0 else "cna",
            url="https://example.com/results",
            published_at=f"2026-09-{25-i:02d}",
            label="positive" if i % 2 == 0 else "negative",
            confidence=0.9,
            aspect="dividend_policy",
        )
        for i in range(count)
    ]


def test_loaded_filter_preserves_original_rows():
    frame = pd.DataFrame(examples(4))
    selected = filter_examples(frame, "cna", "negative")
    assert selected.sentence_id.tolist() == ["s1", "s3"]
    assert filter_examples(frame, "cna", "positive").empty
    assert len(frame) == 4


def test_quotes_label_confidence_escape_text_and_use_original_source_links():
    card = quote_card(
        '<script>alert("x")</script>',
        "earnings",
        "2026-09-25",
        "https://example.com",
        "positive",
        0.92,
    )
    assert "Model confidence: 92%" in card
    assert "Open original source" in card
    assert "noopener noreferrer" in card
    assert "<script>" not in card
    assert "&lt;script&gt;" in card
    assert "href=" not in quote_card(
        "Text", "earnings", "2026-09-25", "javascript:alert(1)"
    )


class EvidencePageTests(DashboardAppTestCase):
    def quotes(self, app):
        return [item.value for item in app.markdown if 'class="quote"' in item.value]

    def topic_page(self):
        app = self.page("Topics")
        app.button(key="topic_evidence_DBS").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app

    def test_mixed_date_formats_are_sorted_and_displayed_consistently(self):
        rows = examples(3)
        rows[0]["published_at"] = "2026-09-24"
        rows[1]["published_at"] = "2026-09-25T00:05:00+08:00"
        rows[2]["published_at"] = "2026-09-25T00:00:00Z"
        self.request.side_effect = fake_api(evidence_rows=rows)
        app = self.topic_page()
        quotes = self.quotes(app)
        self.assertIn("Evidence sentence 2.", quotes[0])
        self.assertIn("Evidence sentence 1.", quotes[1])
        self.assertIn("2026-09-24", quotes[1])
        self.assertIn("Evidence sentence 0.", quotes[2])
        self.assertTrue(
            any("(UTC): 24 Sep 2026–25 Sep 2026" in item.value for item in app.caption)
        )

    def test_paging_filters_reset_and_zero_matches_keep_loaded_scope_clear(self):
        self.request.side_effect = fake_api(evidence_rows=examples())
        app = self.topic_page()
        self.assertEqual(len(self.quotes(app)), 10)
        self.assertIn("Evidence sentence 0.", self.quotes(app)[0])
        self.assertTrue(any("25 most recent" in item.value for item in app.caption))
        app.button(key="evidence_more").click().run()
        self.assertEqual(len(self.quotes(app)), 20)
        app.selectbox(key="evidence_source").set_value("cna").run()
        self.assertEqual(len(self.quotes(app)), 10)  # filters restart paging
        self.assertTrue(all("CNA" in quote for quote in self.quotes(app)))
        app.selectbox(key="evidence_sentiment").set_value("positive").run()
        self.assertEqual(len(self.quotes(app)), 0)
        self.assertTrue(any("loaded examples" in item.value for item in app.info))
        app.button(key="evidence_reset").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(len(self.quotes(app)), 10)
        self.assertEqual(app.selectbox(key="evidence_source").value, "ALL")
        self.assertEqual(app.selectbox(key="evidence_sentiment").value, "ALL")
        app.selectbox(key="evidence_source").set_value("cna").run()
        app.selectbox(key="evidence_bank").set_value("UOB").run()
        self.assertEqual(app.selectbox(key="evidence_source").value, "ALL")

    def test_overall_browse_does_not_invent_sentiment_labels(self):
        app = self.page("Evidence")
        self.assertTrue(app.selectbox(key="evidence_sentiment").disabled)
        self.assertTrue(
            any("Choose a specific topic" in item.value for item in app.caption)
        )
        self.assertTrue(
            all("Model confidence:" not in quote for quote in self.quotes(app))
        )
