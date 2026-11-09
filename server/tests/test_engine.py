import pytest

from app.engine import EngineError, run_tool


def make_engine(tmp_path, body):
    d = tmp_path / "engine" / "trader-scanner"
    d.mkdir(parents=True)
    (d / "scan.py").write_text(body)
    return tmp_path / "engine"


def test_run_tool_returns_parsed_json(tmp_path):
    eng = make_engine(tmp_path, 'import json,sys\nprint(json.dumps({"ok": True, "args": sys.argv[1:]}))')
    out = run_tool("scanner", ["orb"], tmp_path, engine_dir=eng)
    assert out == {"ok": True, "args": ["orb", "--json"]}


def test_run_tool_raises_engine_error_on_nonzero_exit(tmp_path):
    eng = make_engine(tmp_path, 'import sys\nsys.stderr.write("yahoo fora")\nsys.exit(2)')
    with pytest.raises(EngineError) as e:
        run_tool("scanner", [], tmp_path, engine_dir=eng)
    assert e.value.returncode == 2
    assert "yahoo fora" in e.value.stderr


def test_run_tool_uses_workdir_as_cwd(tmp_path):
    eng = make_engine(tmp_path, 'import json,os\nprint(json.dumps({"cwd": os.getcwd()}))')
    work = tmp_path / "w"
    out = run_tool("scanner", [], work, engine_dir=eng)
    assert out["cwd"] == str(work.resolve())


def test_run_tool_non_json_output_is_engine_error(tmp_path):
    eng = make_engine(tmp_path, 'print("not json")')
    with pytest.raises(EngineError):
        run_tool("scanner", [], tmp_path, engine_dir=eng)


def test_run_tool_accepts_nonzero_exit_when_stdout_is_json(tmp_path):
    # news.py usa exit 1 para dizer "há algo novo"; o JSON continua válido.
    eng = make_engine(tmp_path, 'import sys\nprint("{\\"moves\\": []}")\nsys.exit(1)')
    assert run_tool("scanner", [], tmp_path, engine_dir=eng) == {"moves": []}
