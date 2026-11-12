"""Screen language selection (English / Korean)."""

import json
import re
import string

import pytest

from toolcall_conformance import i18n
from toolcall_conformance.checks import all_checks
from toolcall_conformance.cli import main
from toolcall_conformance.mock import MODES
from toolcall_conformance.targets import TargetsError, make_target

# A fixed Korean particle right after a placeholder (optionally after a closing quote/bracket/space).
PLACEHOLDER_PARTICLE = re.compile(r"\}[\"'\)\]\s`]*(이|가|을|를|은|는|과|와|도|으로|로)(?![가-힣])")


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def fields(text):
    return sorted(f[1] for f in string.Formatter().parse(text) if f[1] is not None)


def test_key_sets_and_placeholders_match():
    en, ko = i18n.MESSAGES["en"], i18n.MESSAGES["ko"]
    assert set(en) == set(ko)
    for key in en:
        assert fields(en[key]) == fields(ko[key]), key


def test_every_check_and_mode_has_text():
    for c in all_checks():
        assert i18n.MESSAGES["en"][f"check.{c.id}"] == c.summary
        assert f"check.{c.id}" in i18n.MESSAGES["ko"]
    for name, fault in MODES.items():
        assert i18n.mode_description(name, "", "en") == fault.description
        assert i18n.mode_description(name, "", "ko") != fault.description


def test_no_fixed_particle_after_placeholder():
    for key, text in i18n.MESSAGES["ko"].items():
        assert not PLACEHOLDER_PARTICLE.search(text), (key, text)
    assert PLACEHOLDER_PARTICLE.search('"{x}" 가')  # the guard itself works


def test_precedence(monkeypatch):
    monkeypatch.setenv("LC_ALL", "ko_KR.UTF-8")
    assert i18n.detect() == "en"  # TOOLCALL_CONFORMANCE_LANG=en wins over LC_ALL
    monkeypatch.delenv("TOOLCALL_CONFORMANCE_LANG")
    assert i18n.detect() == "ko"
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    assert i18n.detect() == "en"  # LC_ALL beats LANG
    monkeypatch.delenv("LC_ALL")
    assert i18n.detect() == "ko"
    monkeypatch.setenv("LANG", "C")
    assert i18n.detect() == "en"


def test_flag_beats_env(capsys, monkeypatch):
    monkeypatch.setenv("TOOLCALL_CONFORMANCE_LANG", "ko")
    assert "Checks:" in run(capsys, "--lang", "en", "list")[1]
    assert "검사:" in run(capsys, "list")[1]
    assert "검사:" in run(capsys, "list", "--lang", "ko")[1]


def test_locale_fallback_korean(capsys, monkeypatch):
    monkeypatch.delenv("TOOLCALL_CONFORMANCE_LANG")
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    assert "검사:" in run(capsys, "list")[1]


def test_help_is_korean(capsys):
    with pytest.raises(SystemExit) as top:
        main(["--lang", "ko", "--help"])
    assert top.value.code == 0
    out = capsys.readouterr().out
    assert "사용법:" in out and "도구 호출" in out and "화면 언어" in out
    with pytest.raises(SystemExit):
        main(["run", "--lang", "ko", "--help"])
    out = capsys.readouterr().out
    assert "사용법:" in out and "서버에서 쓰는 모델 이름" in out


def test_help_english_default(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "usage:" in out and "screen language" in out


def test_argparse_errors_localized(capsys):
    for argv, text in ((["--lang", "ko", "nope"], "잘못된 선택입니다"),
                       (["--lang", "ko"], "필요합니다"),
                       (["--lang", "ko", "list", "--bogus"], "알 수 없는 인자")):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "오류:" in err and text in err, err
    with pytest.raises(SystemExit) as exc:
        main(["nope"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_invalid_lang_value_is_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--lang", "fr", "list"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_list_korean(capsys):
    code, out, _ = run(capsys, "--lang", "ko", "list")
    assert code == 0 and "검사:" in out and "목 모드:" in out
    assert "nonstream_basic" in out and "[Gemini OpenAI-compat forum report]" in out


def test_demo_text_korean(capsys):
    code, out, _ = run(capsys, "--lang", "ko", "demo")
    assert code == 0
    lines = out.splitlines()
    assert "연습용" in lines[0] and "not results" not in lines[0]
    assert any(line.startswith("대상") for line in lines)
    assert any(line.startswith("요약: ") for line in lines)
    assert "목 모드:" in lines[-1]
    assert "FAIL" in out  # grade tokens stay as they are


def test_demo_banner_single_language(capsys):
    first = run(capsys, "demo")[1].splitlines()[0]
    assert not re.search(r"[가-힣]", first)


def test_demo_markdown_korean(capsys):
    out = run(capsys, "--lang", "ko", "demo", "--format", "md")[1]
    assert out.startswith("> [mock] 내장") and "| 대상 |" in out


def test_json_identical_across_languages(capsys):
    a = run(capsys, "--lang", "en", "demo", "--format", "json")[1]
    b = run(capsys, "--lang", "ko", "demo", "--format", "json")[1]
    # the mock server picks a random port per run; everything else must be identical
    assert json.loads(re.sub(r"127\.0\.0\.1:\d+", "HOST", a)) == json.loads(re.sub(r"127\.0\.0\.1:\d+", "HOST", b))


def test_targets_error_localized_but_str_english(capsys):
    with pytest.raises(TargetsError) as exc:
        make_target("t", "ftp://x", "m")
    assert "must start with http:// or https://" in str(exc.value)
    assert exc.value.code == "url_scheme_target"
    code, _, err = run(capsys, "--lang", "ko", "run", "--base-url", "ftp://x", "--model", "m")
    assert code == 2 and err.startswith("오류:") and "http://" in err and "must start" not in err
    code, _, err = run(capsys, "--lang", "ko", "run", "--only", "x")
    assert code == 2 and "--base-url" in err and "give --base-url" not in err
    code, _, err = run(capsys, "--lang", "ko", "run", "--base-url", "http://127.0.0.1:1/v1",
                       "--model", "m", "--only", "bogus")
    assert code == 2 and "알 수 없는 검사 ID" in err


def test_connect_error_korean(capsys):
    code, _, err = run(capsys, "--lang", "ko", "run", "--base-url", "http://127.0.0.1:1/v1", "--model", "m")
    assert code == 2 and "\n오류: cannot connect" in err and "서버가 실행 중인지" in err


def test_set_lang_rejects_unknown():
    with pytest.raises(ValueError, match="unsupported language"):
        i18n.set_lang("fr")


def _display_width(text):
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_text_table_columns_align_by_display_width(capsys, lang):
    code, out, _ = run(capsys, "--lang", lang, "demo")
    lines = out.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(("target", "대상")))
    header, rows = lines[start], lines[start + 2:start + 2 + len(MODES)]
    assert len(rows) == len(MODES)
    cols = header.split()[1:]
    # every column starts at the same display column in the header and in every row
    def starts(line):
        pos, found, prev_space = 0, [], True
        for ch in line:
            if ch != " " and prev_space:
                found.append(pos)
            prev_space = ch == " "
            pos += _display_width(ch)
        return found
    assert starts(header)[1:] == starts(rows[0])[1:] == starts(rows[-1])[1:]
    assert len(cols) == len(starts(header)) - 1


def test_korean_url_error_names_target_in_korean(capsys):
    code, _, err = run(capsys, "--lang", "ko", "run", "--base-url", "ftp://x", "--model", "m")
    assert code == 2 and "대상 'ftp://x'" in err and "target" not in err


def test_korean_skipped_target_line_is_korean(capsys, tmp_path, monkeypatch):
    monkeypatch.delenv("NOPE_KEY_X", raising=False)
    f = tmp_path / "t.toml"
    f.write_text('[[target]]\nname = "b"\nbase_url = "http://127.0.0.1:1/v1"\nmodel = "m"\n'
                 'api_key_env = "NOPE_KEY_X"\n', encoding="utf-8")
    code, _, err = run(capsys, "--lang", "ko", "run", "--targets", str(f))
    assert code == 2 and "대상 건너뜀 b: 대상 'b': 환경 변수가 설정되지 않았습니다: NOPE_KEY_X" in err
    assert "is not set" not in err


def test_missing_lang_value_reports_error_once(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--lang"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert err.count("--lang") >= 1 and err.count("usage:") + err.count("사용법:") == 1
