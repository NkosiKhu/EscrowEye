from __future__ import annotations

import json

from agent.prompts import (
    ASSISTANT_SYSTEM_PROMPT,
    STAGE1_REVIEWER_PROMPT,
    STAGE2_SUMMARY_PROMPT,
)


class TestAssistantPrompt:
    def test_render_with_user_info(self):
        rendered = ASSISTANT_SYSTEM_PROMPT.format(user_id=42, user_type="owner")
        assert "42" in rendered
        assert "owner" in rendered
        assert "EscrowEye" in rendered

    def test_render_supplier(self):
        rendered = ASSISTANT_SYSTEM_PROMPT.format(user_id=7, user_type="supplier")
        assert "7" in rendered
        assert "supplier" in rendered
        assert "tools" in rendered

    def test_contains_rules(self):
        rendered = ASSISTANT_SYSTEM_PROMPT.format(user_id=1, user_type="owner")
        assert "402 Payment Required" in rendered
        assert "destructive actions" in rendered
        assert "HashPack" in rendered


class TestStage1ReviewerPrompt:
    def test_render_with_rooms_and_image(self):
        rooms = [{"id": 1, "name": "Kitchen"}, {"id": 2, "name": "Bathroom"}]
        rendered = STAGE1_REVIEWER_PROMPT.format(
            job_id=5,
            rooms_with_ids=json.dumps(rooms, indent=2),
            base64_image="/9j/4AAQ...",
        )
        assert "job #5" in rendered
        assert "Kitchen" in rendered
        assert "Bathroom" in rendered
        assert "JSON" in rendered
        assert "room_id" in rendered
        assert "cleanliness_score" in rendered
        assert "pass" in rendered

    def test_contains_expected_keys(self):
        rooms = [{"id": 1, "name": "Kitchen"}]
        rendered = STAGE1_REVIEWER_PROMPT.format(
            job_id=1,
            rooms_with_ids=json.dumps(rooms),
            base64_image="base64data",
        )
        assert "confidence" in rendered
        assert "issues" in rendered
        assert "room_name" in rendered


class TestStage2SummaryPrompt:
    def test_render_with_stage1_results(self):
        rooms = [{"id": 1, "name": "Kitchen"}, {"id": 2, "name": "Bathroom"}]
        stage1 = [
            {"photo_id": 1, "room_name": "Kitchen", "pass": True},
            {"photo_id": 2, "room_name": "Bathroom", "pass": False},
        ]
        rendered = STAGE2_SUMMARY_PROMPT.format(
            job_id=3,
            rooms_with_ids=json.dumps(rooms, indent=2),
            stage_1_results=json.dumps(stage1, indent=2),
        )
        assert "job #3" in rendered
        assert "Kitchen" in rendered
        assert "Bathroom" in rendered
        assert "overall_pass" in rendered
        assert "room_assignments" in rendered
        assert "retake_needed" in rendered

    def test_contains_decision_instructions(self):
        rendered = STAGE2_SUMMARY_PROMPT.format(
            job_id=1,
            rooms_with_ids="[]",
            stage_1_results="[]",
        )
        assert "Which photos pass/fail" in rendered
        assert "Associate each photo" in rendered
        assert "overall verdict" in rendered.lower()
