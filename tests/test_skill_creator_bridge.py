#!/usr/bin/env python3
"""
Tests for skill_creator_bridge module.

Tests the skill-creator detection, handoff logic, and inter-skill communication.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Add shared dir to path
SHARED_DIR = Path(__file__).parent.parent / "skills" / "_shared"
sys.path.insert(0, str(SHARED_DIR))

from skill_creator_bridge import (
    DEFAULT_HANDOFF_THRESHOLD,
    SKILL_CREATOR_PATHS,
    format_handoff_message,
    generate_handoff_context,
    get_skill_creator_instructions,
    get_skill_creator_path,
    is_skill_creator_available,
    should_handoff,
)


class TestSkillCreatorDetection:
    """Tests for skill-creator availability detection."""

    def test_skill_creator_not_installed(self, tmp_path):
        """Test detection when skill-creator is not installed."""
        with mock.patch(
            "skill_creator_bridge.SKILL_CREATOR_PATHS",
            [tmp_path / "nonexistent"],
        ):
            assert not is_skill_creator_available()
            assert get_skill_creator_path() is None

    def test_skill_creator_installed(self, tmp_path):
        """Test detection when skill-creator is installed."""
        skill_creator_dir = tmp_path / "skill-creator"
        skill_creator_dir.mkdir()
        (skill_creator_dir / "SKILL.md").write_text("# Skill Creator")

        with mock.patch(
            "skill_creator_bridge.SKILL_CREATOR_PATHS",
            [skill_creator_dir],
        ):
            assert is_skill_creator_available()
            assert get_skill_creator_path() == skill_creator_dir

    def test_skill_creator_installed_alternative_name(self, tmp_path):
        """Test detection with underscore naming convention."""
        skill_creator_dir = tmp_path / "skill_creator"
        skill_creator_dir.mkdir()
        (skill_creator_dir / "SKILL.md").write_text("# Skill Creator")

        with mock.patch(
            "skill_creator_bridge.SKILL_CREATOR_PATHS",
            [tmp_path / "nonexistent", skill_creator_dir],
        ):
            assert is_skill_creator_available()
            assert get_skill_creator_path() == skill_creator_dir

    def test_skill_creator_missing_skill_md(self, tmp_path):
        """Test detection when directory exists but SKILL.md is missing."""
        skill_creator_dir = tmp_path / "skill-creator"
        skill_creator_dir.mkdir()
        # No SKILL.md file

        with mock.patch(
            "skill_creator_bridge.SKILL_CREATOR_PATHS",
            [skill_creator_dir],
        ):
            assert not is_skill_creator_available()


class TestShouldHandoff:
    """Tests for handoff decision logic (Option B + Option C)."""

    def test_high_confidence_no_handoff(self):
        """Test that high confidence prevents handoff."""
        do_handoff, reason = should_handoff(
            confidence_score=0.8,
            force_handoff=False,
            disable_handoff=False,
        )
        assert not do_handoff
        assert "High confidence" in reason

    def test_low_confidence_handoff_when_available(self, tmp_path):
        """Test that low confidence triggers handoff when skill-creator available."""
        skill_creator_dir = tmp_path / "skill-creator"
        skill_creator_dir.mkdir()
        (skill_creator_dir / "SKILL.md").write_text("# Skill Creator")

        with mock.patch(
            "skill_creator_bridge.SKILL_CREATOR_PATHS",
            [skill_creator_dir],
        ):
            do_handoff, reason = should_handoff(
                confidence_score=0.3,
                force_handoff=False,
                disable_handoff=False,
            )
            assert do_handoff
            assert "Low confidence" in reason

    def test_low_confidence_no_handoff_when_unavailable(self, tmp_path):
        """Test that low confidence doesn't handoff when skill-creator unavailable."""
        with mock.patch(
            "skill_creator_bridge.SKILL_CREATOR_PATHS",
            [tmp_path / "nonexistent"],
        ):
            do_handoff, reason = should_handoff(
                confidence_score=0.3,
                force_handoff=False,
                disable_handoff=False,
            )
            assert not do_handoff
            assert "not installed" in reason

    def test_force_handoff_overrides_confidence(self, tmp_path):
        """Test that --use-skill-creator forces handoff regardless of confidence."""
        skill_creator_dir = tmp_path / "skill-creator"
        skill_creator_dir.mkdir()
        (skill_creator_dir / "SKILL.md").write_text("# Skill Creator")

        with mock.patch(
            "skill_creator_bridge.SKILL_CREATOR_PATHS",
            [skill_creator_dir],
        ):
            do_handoff, reason = should_handoff(
                confidence_score=0.9,  # Very high confidence
                force_handoff=True,  # But user forced handoff
                disable_handoff=False,
            )
            assert do_handoff
            assert "User requested" in reason

    def test_force_handoff_fails_when_unavailable(self, tmp_path):
        """Test that force handoff fails gracefully when skill-creator not installed."""
        with mock.patch(
            "skill_creator_bridge.SKILL_CREATOR_PATHS",
            [tmp_path / "nonexistent"],
        ):
            do_handoff, reason = should_handoff(
                confidence_score=0.9,
                force_handoff=True,
                disable_handoff=False,
            )
            assert not do_handoff
            assert "not installed" in reason

    def test_disable_handoff_overrides_everything(self, tmp_path):
        """Test that --no-skill-creator disables handoff completely."""
        skill_creator_dir = tmp_path / "skill-creator"
        skill_creator_dir.mkdir()
        (skill_creator_dir / "SKILL.md").write_text("# Skill Creator")

        with mock.patch(
            "skill_creator_bridge.SKILL_CREATOR_PATHS",
            [skill_creator_dir],
        ):
            do_handoff, reason = should_handoff(
                confidence_score=0.1,  # Very low confidence
                force_handoff=False,
                disable_handoff=True,  # But user disabled handoff
            )
            assert not do_handoff
            assert "User disabled" in reason

    def test_custom_threshold(self):
        """Test that custom threshold is respected."""
        # With default threshold (0.5), 0.4 would trigger handoff
        # With custom threshold (0.3), 0.4 should NOT trigger handoff
        do_handoff, reason = should_handoff(
            confidence_score=0.4,
            force_handoff=False,
            disable_handoff=False,
            threshold=0.3,
        )
        assert not do_handoff
        assert "High confidence" in reason


class TestHandoffContext:
    """Tests for handoff context generation."""

    def test_generate_basic_context(self):
        """Test basic context generation."""
        context = generate_handoff_context(
            source="https://github.com/user/repo",
            source_type="workflow_generation",
            scope="user",
            target_dir="/home/user/.claude/skills/repo-workflow",
            analysis={
                "detected_patterns": ["build_file", "documentation"],
                "language": "Python",
                "frameworks": [],
                "confidence_score": 0.4,
            },
        )

        assert context["handoff_type"] == "skill_creation"
        assert context["source_skill"] == "mine"
        assert context["request"]["source_repo"] == "https://github.com/user/repo"
        assert context["request"]["source_type"] == "workflow_generation"
        assert context["constraints"]["scope"] == "user"
        assert context["constraints"]["dry_run"] is True

    def test_generate_context_with_source_content(self):
        """Test context generation with source content."""
        context = generate_handoff_context(
            source="https://github.com/user/repo",
            source_type="workflow_generation",
            scope="user",
            target_dir="/home/user/.claude/skills/repo-workflow",
            analysis={"confidence_score": 0.4},
            source_content={
                "readme": "# My Project\n\nA cool project.",
                "prompts": ["system prompt 1", "system prompt 2"],
                "docs": ["doc1.md content", "doc2.md content"],
            },
        )

        assert "source_content" in context["request"]
        assert context["request"]["source_content"]["readme"] == "# My Project\n\nA cool project."
        assert len(context["request"]["source_content"]["prompts"]) == 2


class TestSkillCreatorRequestFile:
    """Tests for skill request file creation."""

    def test_create_request_file(self, tmp_path):
        """Test creating a request file at a specific path."""
        target_path = tmp_path / "request.json"
        context = {"test": "data", "handoff_type": "skill_creation"}

        from skill_creator_bridge import create_skill_request_file

        result = create_skill_request_file(context, output_path=target_path)

        assert result == target_path
        assert target_path.exists()

        with open(target_path) as f:
            saved_data = json.load(f)
            assert saved_data == context

    def test_create_request_file_default(self, tmp_path):
        """Test creating a request file at the default path (mocked)."""
        context = {"test": "data"}
        default_path = tmp_path / "default_request.json"

        # Mock Path.home() to point to tmp_path so we can verify file creation
        with mock.patch("pathlib.Path.home", return_value=tmp_path):
            from skill_creator_bridge import create_skill_request_file

            # The function uses Path.home() / ".claude" / "mine" / "skill_creator_request.json"
            expected_path = tmp_path / ".claude" / "mine" / "skill_creator_request.json"

            result = create_skill_request_file(context)

            assert result == expected_path
            assert expected_path.exists()

            with open(expected_path) as f:
                saved_data = json.load(f)
                assert saved_data == context


class TestHandoffMessage:
    """Tests for human-readable handoff message formatting."""

    def test_format_basic_message(self):
        """Test basic message formatting."""
        context = {
            "request": {
                "source_repo": "https://github.com/user/repo",
                "analysis": {
                    "reason_for_handoff": "Low confidence in template conversion",
                    "confidence_score": 0.35,
                },
            },
            "constraints": {
                "target_dir": "/home/user/.claude/skills/repo-workflow",
                "scope": "user",
            },
        }

        message = format_handoff_message(context, verbose=False)

        assert "SKILL-CREATOR HANDOFF" in message
        assert "https://github.com/user/repo" in message
        assert "Low confidence" in message
        assert "35" in message  # 35% confidence

    def test_format_verbose_message(self):
        """Test verbose message includes additional details."""
        context = {
            "request": {
                "source_repo": "https://github.com/user/repo",
                "analysis": {
                    "reason_for_handoff": "Low confidence",
                    "confidence_score": 0.35,
                    "language": "Python",
                    "frameworks": ["custom"],
                    "detected_patterns": ["agent", "tool"],
                },
            },
            "constraints": {
                "target_dir": "/home/user/.claude/skills/repo-workflow",
                "scope": "user",
            },
        }

        message = format_handoff_message(context, verbose=True)

        assert "Language: Python" in message
        assert "Frameworks: custom" in message


class TestSkillCreatorInstructions:
    """Tests for skill-creator instruction generation."""

    def test_generate_instructions(self):
        """Test basic instruction generation."""
        instructions = get_skill_creator_instructions(
            source="https://github.com/user/repo",
            description="workflow automation for data processing",
            target_scope="user",
        )

        assert "Skill-Creator Handoff" in instructions
        assert "https://github.com/user/repo" in instructions
        assert "workflow automation for data processing" in instructions
        assert "user" in instructions


class TestDefaultThreshold:
    """Tests for default threshold constant."""

    def test_default_threshold_value(self):
        """Test that default threshold is reasonable."""
        assert 0.0 < DEFAULT_HANDOFF_THRESHOLD < 1.0
        assert DEFAULT_HANDOFF_THRESHOLD == 0.5  # Conservative default
