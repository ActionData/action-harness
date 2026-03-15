"""Tests for prompt-to-slug conversion."""

from action_harness.slugify import slugify_prompt


class TestSlugifyPrompt:
    def test_basic_text(self) -> None:
        assert slugify_prompt("Fix the auth bug") == "fix-the-auth-bug"

    def test_special_characters(self) -> None:
        assert slugify_prompt("Fix bug in issue #42") == "fix-bug-in-issue-42"

    def test_long_prompt_truncation(self) -> None:
        long_prompt = "a" * 100
        result = slugify_prompt(long_prompt)
        assert len(result) <= 50

    def test_custom_max_length(self) -> None:
        result = slugify_prompt("Fix the auth bug in the module", max_length=10)
        assert len(result) <= 10

    def test_unicode(self) -> None:
        result = slugify_prompt("Fix the büg with émojis 🚀")
        # Unicode chars should be replaced with hyphens, collapsed
        assert result == "fix-the-b-g-with-mojis"

    def test_empty_string(self) -> None:
        assert slugify_prompt("") == ""

    def test_multiline_prompt_uses_first_line(self) -> None:
        result = slugify_prompt("Fix the auth bug\nAlso update tests\nAnd more")
        assert result == "fix-the-auth-bug"

    def test_consecutive_special_chars_collapsed(self) -> None:
        result = slugify_prompt("Fix --- the   bug!!!")
        assert result == "fix-the-bug"

    def test_leading_trailing_hyphens_stripped(self) -> None:
        result = slugify_prompt("!!!Fix bug!!!")
        assert result == "fix-bug"

    def test_truncation_strips_trailing_hyphens(self) -> None:
        # Construct a prompt that when truncated would end with a hyphen
        result = slugify_prompt("abcde fghij", max_length=6)
        # "abcde-fghij" truncated to 6 = "abcde-", trailing hyphen stripped
        assert result == "abcde"

    def test_only_special_chars(self) -> None:
        result = slugify_prompt("!!@@##$$")
        assert result == ""

    def test_numbers_preserved(self) -> None:
        result = slugify_prompt("Fix issue 123")
        assert result == "fix-issue-123"

    def test_mixed_case(self) -> None:
        result = slugify_prompt("Add README Update")
        assert result == "add-readme-update"
