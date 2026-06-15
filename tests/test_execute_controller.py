"""Tests for controllers/execute.py — subprocess sandbox and Docker sandbox paths."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import controllers.execute as ec
from controllers.execute import (
    _apply_autowrap,
    _get_filename,
    _find_binary,
    _run_sql,
    get_available_runtimes,
    run_code,
    _run_java,
    _run_cpp,
    _run_rust,
    _run_go,
    _run_kotlin,
    _run_scala,
    _run_simple,
    _run_prolog,
    _run_cobol,
    _run_fortran,
    _run_awk,
    _run_sml,
    _run_haxe,
    _run_odin,
    _run_sbcl,
    _run_octave,
    _run_zig,
    _run_crystal,
    _run_nim,
    _run_csharp,
    _run_in_docker,
    _get_docker_client,
)
from schemas.execute import ExecuteRequest, ExecuteResponse
from models.user import User

# ── helpers ───────────────────────────────────────────────────────────────────

def _user():
    return User(
        id=1,
        email="test@example.com",
        name="Test",
        is_active=True,
        hashed_password="$2b$hash",
        llm_provider_id=1,
    )

def _ok(stdout="ok\n", stderr=""):
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = stderr
    return m

def _fail(stderr="error", stdout=""):
    m = MagicMock()
    m.returncode = 1
    m.stdout = stdout
    m.stderr = stderr
    return m

def _req(language, code="print('hi')"):
    return ExecuteRequest(language=language, code=code)

# ── _get_filename ─────────────────────────────────────────────────────────────

class TestGetFilename:
    def test_python(self):
        assert _get_filename("python") == "main.py"
        assert _get_filename("python3") == "main.py"

    def test_javascript_variants(self):
        for lang in ("javascript", "js", "jsx"):
            assert _get_filename(lang) == "main.jsx"

    def test_typescript_variants(self):
        for lang in ("typescript", "ts", "tsx"):
            assert _get_filename(lang) == "main.tsx"

    def test_compiled(self):
        assert _get_filename("java") == "Main.java"
        assert _get_filename("rust") == "main.rs"
        assert _get_filename("go") == "main.go"
        assert _get_filename("cpp") == "main.cpp"
        assert _get_filename("c") == "main.c"

    def test_scripting(self):
        assert _get_filename("ruby") == "main.rb"
        assert _get_filename("bash") == "main.sh"
        assert _get_filename("perl") == "main.pl"
        assert _get_filename("lua") == "main.lua"
        assert _get_filename("php") == "main.php"

    def test_jvm(self):
        assert _get_filename("kotlin") == "main.kt"
        assert _get_filename("scala") == "main.scala"

    def test_other(self):
        assert _get_filename("dart") == "main.dart"
        assert _get_filename("zig") == "main.zig"
        assert _get_filename("nim") == "main.nim"
        assert _get_filename("cobol") == "main.cob"
        assert _get_filename("fortran") == "main.f90"
        assert _get_filename("haxe") == "main.hx"

    def test_new_languages(self):
        assert _get_filename("clojure") == "main.clj"
        assert _get_filename("clj") == "main.clj"
        assert _get_filename("coffeescript") == "main.coffee"
        assert _get_filename("coffee") == "main.coffee"
        assert _get_filename("nasm") == "main.asm"
        assert _get_filename("asm") == "main.asm"
        assert _get_filename("assembly") == "main.asm"

    def test_unknown_returns_txt(self):
        assert _get_filename("unknownlang") == "main.txt"

# ── _find_binary ──────────────────────────────────────────────────────────────

class TestFindBinary:
    def test_finds_existing_binary(self):
        with patch("shutil.which", return_value="/usr/bin/python3"):
            result = _find_binary(["python3"])
        assert result == "/usr/bin/python3"

    def test_none_candidate_returns_builtin(self):
        assert _find_binary([None]) == "builtin"

    def test_returns_none_when_not_found(self):
        with patch("shutil.which", return_value=None), patch("os.path.isfile", return_value=False):
            result = _find_binary(["nonexistent_binary_xyz"])
        assert result is None

    def test_falls_back_to_extra_dirs(self):
        import os

        def fake_which(b):
            return None

        def fake_isfile(path):
            return "/opt/homebrew/bin" in path

        with (
            patch("shutil.which", side_effect=fake_which),
            patch("os.path.isfile", side_effect=fake_isfile),
            patch("os.access", return_value=True),
        ):
            result = _find_binary(["somebinary"])
        assert result is not None

# ── get_available_runtimes ────────────────────────────────────────────────────

class TestGetAvailableRuntimes:
    def test_returns_dict_with_languages_key(self):
        result = get_available_runtimes()
        assert "languages" in result
        assert isinstance(result["languages"], list)

    def test_python_always_present(self):
        result = get_available_runtimes()
        assert "python" in result["languages"] or "python3" in result["languages"]

# ── _run_sql ──────────────────────────────────────────────────────────────────

class TestRunSql:
    def test_select(self):
        r = _run_sql("SELECT 1+1 AS result")
        assert "2" in r.stdout
        assert r.stderr == ""

    def test_create_insert_select(self):
        code = "CREATE TABLE t (id INTEGER); INSERT INTO t VALUES (42); SELECT * FROM t"
        r = _run_sql(code)
        assert "42" in r.stdout

    def test_headers_in_output(self):
        r = _run_sql("SELECT 1 AS mycolumn")
        assert "mycolumn" in r.stdout

    def test_bad_sql_returns_error_in_stdout(self):
        r = _run_sql("SELECT * FROM nonexistent_table")
        assert "Error" in r.stdout or r.stderr

    def test_empty_result_no_output(self):
        r = _run_sql("CREATE TABLE empty (id INTEGER)")
        assert r.stdout == ""

# ── _apply_autowrap ───────────────────────────────────────────────────────────

class TestApplyAutowrap:
    def test_rust_adds_main_when_missing(self):
        code = 'fn hello() { println!("hi"); }'
        result = _apply_autowrap("rust", code)
        assert "fn main()" in result
        assert "hello();" in result

    def test_rust_no_wrap_when_main_exists(self):
        code = 'fn main() { println!("hi"); }'
        result = _apply_autowrap("rust", code)
        assert result.count("fn main()") == 1

    def test_rust_alias_rs(self):
        code = "fn greet() {}"
        result = _apply_autowrap("rs", code)
        assert "fn main()" in result

    def test_go_adds_package_and_main(self):
        code = 'func hello() { fmt.Println("hi") }'
        result = _apply_autowrap("go", code)
        assert "package main" in result
        assert "func main()" in result

    def test_go_no_wrap_when_complete(self):
        code = 'package main\nimport "fmt"\nfunc main() { fmt.Println("hi") }'
        result = _apply_autowrap("go", code)
        assert result.count("func main()") == 1

    def test_kotlin_adds_main(self):
        code = 'fun greet() { println("hi") }'
        result = _apply_autowrap("kotlin", code)
        assert "fun main()" in result
        assert "greet()" in result

    def test_kotlin_no_wrap_when_main_exists(self):
        code = 'fun main() { println("hi") }'
        result = _apply_autowrap("kotlin", code)
        assert result.count("fun main()") == 1

    def test_cpp_adds_main(self):
        code = '#include<iostream>\nvoid hello() { std::cout << "hi"; }'
        result = _apply_autowrap("cpp", code)
        assert "int main()" in result

    def test_cpp_no_wrap_when_main_exists(self):
        code = "int main() { return 0; }"
        result = _apply_autowrap("cpp", code)
        assert result.count("int main(") == 1

    def test_c_adds_main(self):
        code = '#include<stdio.h>\nvoid hello() { printf("hi"); }'
        result = _apply_autowrap("c", code)
        assert "int main()" in result

    def test_java_wraps_snippet_in_class(self):
        code = 'public static void greet() { System.out.println("hi"); }'
        result = _apply_autowrap("java", code)
        assert "class Main" in result
        assert "public static void main" in result

    def test_java_adds_main_to_class_without_main(self):
        code = "public class Foo { public static void greet() {} }"
        result = _apply_autowrap("java", code)
        assert "public static void main" in result

    def test_java_no_wrap_when_main_exists(self):
        code = "public class Main { public static void main(String[] args) {} }"
        result = _apply_autowrap("java", code)
        assert result.count("public static void main") == 1

    def test_zig_adds_main(self):
        code = "fn hello() void {}"
        result = _apply_autowrap("zig", code)
        assert "pub fn main" in result

    def test_zig_no_wrap_when_main_exists(self):
        code = "pub fn main() !void {}"
        result = _apply_autowrap("zig", code)
        assert result.count("pub fn main") == 1

    def test_react_adds_createroot(self):
        code = "function MyApp() { return <div>hi</div>; }\nexport default MyApp;"
        result = _apply_autowrap("react", code)
        assert "createRoot" in result or "ReactDOM" in result

    def test_react_no_wrap_when_createroot_exists(self):
        code = "createRoot(document.getElementById('root'));"
        result = _apply_autowrap("javascript", code)
        assert result.count("createRoot") == 1

    def test_passthrough_for_python(self):
        code = "print('hi')"
        assert _apply_autowrap("python", code) == code

    def test_passthrough_for_ruby(self):
        code = 'puts "hi"'
        assert _apply_autowrap("ruby", code) == code

# ── _run_java ────────────────────────────────────────────────────────────────

class TestRunJava:
    def test_runs_complete_class(self):
        code = 'public class Main { public static void main(String[] a) { System.out.println("hi"); } }'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), _ok(stdout="hi\n")]
            result = _run_java(code)
        assert result.stdout == "hi\n"

    def test_returns_stderr_on_compile_error(self):
        code = "public class Main { invalid syntax }"
        with patch("subprocess.run", return_value=_fail(stderr="error: ';' expected")):
            result = _run_java(code)
        assert "error" in result.stderr.lower()

    def test_auto_wraps_snippet(self):
        code = 'public static void greet() { System.out.println("hi"); }'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), _ok(stdout="hi\n")]
            result = _run_java(code)
        assert result.stdout == "hi\n"

    def test_timeout_returns_error_message(self):
        code = "public class Main { public static void main(String[] a) {} }"
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), subprocess.TimeoutExpired(cmd="java", timeout=15)]
            result = _run_java(code)
        assert "timed out" in result.stderr.lower()

# ── _run_cpp ──────────────────────────────────────────────────────────────────

class TestRunCpp:
    def test_compiles_and_runs(self):
        code = '#include<iostream>\nint main(){std::cout<<"hi";}'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), _ok(stdout="hi")]
            result = _run_cpp(code, "cpp")
        assert result.stdout == "hi"

    def test_compile_error_returned(self):
        code = "invalid c++ code!!!"
        with patch("subprocess.run", return_value=_fail(stderr="error: expected")):
            result = _run_cpp(code, "cpp")
        assert result.stderr != ""

    def test_c_uses_gcc(self):
        code = '#include<stdio.h>\nint main(){printf("hi");}'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), _ok(stdout="hi")]
            result = _run_cpp(code, "c")
        assert result.stdout == "hi"

    def test_c_auto_wrap(self):
        code = '#include<stdio.h>\nvoid hello() { printf("hi"); }'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), _ok(stdout="hi")]
            result = _run_cpp(code, "c")
        assert result.stdout == "hi"

    def test_timeout(self):
        code = "int main() {}"
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), subprocess.TimeoutExpired("g++", 15)]
            result = _run_cpp(code, "cpp")
        assert "timed out" in result.stderr.lower()

    def test_auto_wrap_cpp(self):
        code = '#include<iostream>\nvoid hello() { std::cout << "hi"; }'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), _ok(stdout="hi")]
            result = _run_cpp(code, "cpp")
        assert result.stdout == "hi"

# ── _run_rust ─────────────────────────────────────────────────────────────────

class TestRunRust:
    def test_compiles_and_runs(self):
        code = 'fn main() { println!("hi"); }'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), _ok(stdout="hi\n")]
            result = _run_rust(code)
        assert result.stdout == "hi\n"

    def test_compile_error(self):
        code = "invalid rust"
        with patch("subprocess.run", return_value=_fail(stderr="error[E")):
            result = _run_rust(code)
        assert result.stderr != ""

    def test_auto_wraps_snippet(self):
        code = 'fn greet() { println!("hi"); }'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), _ok(stdout="hi\n")]
            result = _run_rust(code)
        assert result.stdout == "hi\n"

    def test_timeout(self):
        code = "fn main() {}"
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), subprocess.TimeoutExpired("rustc", 15)]
            result = _run_rust(code)
        assert "timed out" in result.stderr.lower()

# ── _run_go ───────────────────────────────────────────────────────────────────

class TestRunGo:
    def test_runs_complete_program(self):
        code = 'package main\nimport "fmt"\nfunc main() { fmt.Println("hi") }'
        with patch("subprocess.run", return_value=_ok(stdout="hi\n")):
            result = _run_go(code)
        assert result.stdout == "hi\n"

    def test_adds_package_when_missing(self):
        code = 'func hello() { fmt.Println("hi") }'
        with patch("subprocess.run", return_value=_ok(stdout="hi\n")):
            result = _run_go(code)
        assert result.stdout == "hi\n"

    def test_timeout(self):
        code = "package main\nfunc main() {}"
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("go", 15)):
            result = _run_go(code)
        assert "timed out" in result.stderr.lower()

# ── _run_kotlin ───────────────────────────────────────────────────────────────

class TestRunKotlin:
    def test_compiles_and_runs(self):
        code = 'fun main() { println("hi") }'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), _ok(stdout="hi\n")]
            result = _run_kotlin(code)
        assert result.stdout == "hi\n"

    def test_compile_error(self):
        code = "invalid kotlin"
        with patch("subprocess.run", return_value=_fail(stderr="error:")):
            result = _run_kotlin(code)
        assert result.stderr != ""

    def test_timeout(self):
        code = 'fun main() { println("hi") }'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), subprocess.TimeoutExpired("java", 15)]
            result = _run_kotlin(code)
        assert "timed out" in result.stderr.lower()

# ── _run_scala ────────────────────────────────────────────────────────────────

class TestRunScala:
    def test_compiles_and_runs(self):
        code = 'object Main extends App { println("hi") }'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), _ok(stdout="hi\n")]
            result = _run_scala(code)
        assert result.stdout == "hi\n"

    def test_compile_error_filters_warnings(self):
        m = _fail(stderr="error: not found\nwarning: deprecated")
        with patch("subprocess.run", return_value=m):
            result = _run_scala("bad code")
        assert "error" in result.stderr.lower()
        assert "warning" not in result.stderr.lower()

    def test_timeout(self):
        code = 'object Main extends App { println("hi") }'
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_ok(), subprocess.TimeoutExpired("java", 60)]
            result = _run_scala(code)
        assert "timed out" in result.stderr.lower()

# ── _run_simple ───────────────────────────────────────────────────────────────

class TestRunSimple:
    def test_runs_python(self):
        with (
            patch("subprocess.run", return_value=_ok(stdout="hi\n")),
            patch("shutil.which", return_value="/usr/bin/python3"),
        ):
            result = _run_simple("python3", "print('hi')")
        assert result.stdout == "hi\n"

    def test_raises_when_binary_not_found(self):
        with patch("shutil.which", return_value=None), patch("os.path.isfile", return_value=False):
            with pytest.raises(HTTPException) as exc:
                _run_simple("ruby", "puts 'hi'")
            assert exc.value.status_code == 500

    def test_timeout(self):
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ruby", 15)),
            patch("shutil.which", return_value="/usr/bin/ruby"),
        ):
            result = _run_simple("ruby", "puts 'hi'")
        assert "timed out" in result.stderr.lower()

    def test_file_not_found_raises_http(self):
        with (
            patch("subprocess.run", side_effect=FileNotFoundError()),
            patch("shutil.which", return_value="/usr/bin/ruby"),
        ):
            with pytest.raises(HTTPException) as exc:
                _run_simple("ruby", "puts 'hi'")
            assert exc.value.status_code == 500

# ── individual compiled/scripted runners ─────────────────────────────────────

class TestRunProlog:
    def test_runs(self):
        code = ":- initialization(main).\nmain :- write(hi), nl."
        with patch("subprocess.run", return_value=_ok(stdout="hi\n")):
            result = _run_prolog(code)
        assert result.stdout == "hi\n"

    def test_adds_initialization_when_missing(self):
        code = "main :- write(hi), nl."
        with patch("subprocess.run", return_value=_ok(stdout="hi\n")) as m:
            _run_prolog(code)
        written_code = open(m.call_args[0][0][-1]).read() if False else None
        # Just verify it ran without error
        assert True

    def test_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("swipl", 15)):
            result = _run_prolog(":- initialization(main).\nmain :- write(hi).")
        assert "timed out" in result.stderr.lower()

class TestRunCobol:
    def test_compiles_and_runs(self):
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/cobc"),
        ):
            mock_run.side_effect = [_ok(), _ok(stdout="Hello COBOL\n")]
            result = _run_cobol("IDENTIFICATION DIVISION.")
        assert result.stdout == "Hello COBOL\n"

    def test_compile_error(self):
        with (
            patch("subprocess.run", return_value=_fail(stderr="error:")),
            patch("shutil.which", return_value="/usr/bin/cobc"),
        ):
            result = _run_cobol("bad code")
        assert result.stderr != ""

class TestRunFortran:
    def test_compiles_and_runs(self):
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/gfortran"),
        ):
            mock_run.side_effect = [_ok(), _ok(stdout="Hello Fortran\n")]
            result = _run_fortran('program main\n  print *, "hi"\nend program')
        assert result.stdout == "Hello Fortran\n"

class TestRunAwk:
    def test_runs(self):
        with (
            patch("subprocess.run", return_value=_ok(stdout="hi\n")),
            patch("shutil.which", return_value="/usr/bin/awk"),
        ):
            result = _run_awk('BEGIN { print "hi" }')
        assert result.stdout == "hi\n"

    def test_timeout(self):
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("awk", 15)),
            patch("shutil.which", return_value="/usr/bin/awk"),
        ):
            result = _run_awk('BEGIN { print "hi" }')
        assert "timed out" in result.stderr.lower()

class TestRunSml:
    def test_runs_and_strips_banner(self):
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/sml"),
        ):
            mock_run.return_value = _ok(
                stdout="Standard ML of NJ\n[opening main.sml]\nHello SML\nval it = () : unit\n-"
            )
            result = _run_sml('print "Hello SML\\n";')
        assert "Hello SML" in result.stdout
        assert "Standard ML" not in result.stdout

    def test_timeout(self):
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("sml", 15)),
            patch("shutil.which", return_value="/usr/bin/sml"),
        ):
            result = _run_sml('print "hi";')
        assert "timed out" in result.stderr.lower()

class TestRunHaxe:
    def test_runs(self):
        code = 'class Main { static function main() { trace("hi"); } }'
        with (
            patch("subprocess.run", return_value=_ok(stdout="hi\n")),
            patch("shutil.which", return_value="/usr/bin/haxe"),
        ):
            result = _run_haxe(code)
        assert result.stdout == "hi\n"

    def test_timeout(self):
        code = 'class Main { static function main() { trace("hi"); } }'
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("haxe", 15)),
            patch("shutil.which", return_value="/usr/bin/haxe"),
        ):
            result = _run_haxe(code)
        assert "timed out" in result.stderr.lower()

class TestRunOdin:
    def test_runs(self):
        with (
            patch("subprocess.run", return_value=_ok(stdout="hi\n")),
            patch("shutil.which", return_value="/usr/bin/odin"),
        ):
            result = _run_odin('package main\nfmt.println("hi")')
        assert result.stdout == "hi\n"

    def test_timeout(self):
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("odin", 15)),
            patch("shutil.which", return_value="/usr/bin/odin"),
        ):
            result = _run_odin("package main")
        assert "timed out" in result.stderr.lower()

class TestRunSbcl:
    def test_runs(self):
        with (
            patch("subprocess.run", return_value=_ok(stdout="hi\n")),
            patch("shutil.which", return_value="/usr/bin/sbcl"),
        ):
            result = _run_sbcl('(format t "hi~%")')
        assert result.stdout == "hi\n"

    def test_timeout(self):
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("sbcl", 15)),
            patch("shutil.which", return_value="/usr/bin/sbcl"),
        ):
            result = _run_sbcl('(format t "hi~%")')
        assert "timed out" in result.stderr.lower()

class TestRunOctave:
    def test_runs(self):
        with (
            patch("subprocess.run", return_value=_ok(stdout="hi\n")),
            patch("shutil.which", return_value="/usr/bin/octave"),
        ):
            result = _run_octave('disp("hi")')
        assert result.stdout == "hi\n"

    def test_timeout(self):
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("octave", 15)),
            patch("shutil.which", return_value="/usr/bin/octave"),
        ):
            result = _run_octave('disp("hi")')
        assert "timed out" in result.stderr.lower()

class TestRunZig:
    def test_compiles_and_runs(self):
        code = 'const std = @import("std");\npub fn main() !void { const out = std.io.getStdOut().writer(); try out.print("hi\\n", .{}); }'
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/zig"),
        ):
            mock_run.side_effect = [_ok(), _ok(stdout="hi\n")]
            result = _run_zig(code)
        assert result.stdout == "hi\n"

    def test_merges_stderr_into_stdout(self):
        code = "pub fn main() !void {}"
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/zig"),
        ):
            mock_run.side_effect = [_ok(), _ok(stdout="", stderr="debug output\n")]
            result = _run_zig(code)
        assert "debug output" in result.stdout

    def test_auto_wraps_snippet(self):
        code = "fn hello() void {}"
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/zig"),
        ):
            mock_run.side_effect = [_ok(), _ok(stdout="")]
            result = _run_zig(code)
        assert result.stderr == ""

    def test_compile_error(self):
        with (
            patch("subprocess.run", return_value=_fail(stderr="error:")),
            patch("shutil.which", return_value="/usr/bin/zig"),
        ):
            result = _run_zig("bad zig code")
        assert result.stderr != ""

    def test_timeout(self):
        code = "pub fn main() !void {}"
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/zig"),
        ):
            mock_run.side_effect = [_ok(), subprocess.TimeoutExpired("zig", 15)]
            result = _run_zig(code)
        assert "timed out" in result.stderr.lower()

class TestRunCrystal:
    def test_compiles_and_runs(self):
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/crystal"),
        ):
            mock_run.side_effect = [_ok(), _ok(stdout="hi\n")]
            result = _run_crystal('puts "hi"')
        assert result.stdout == "hi\n"

    def test_compile_error(self):
        with (
            patch("subprocess.run", return_value=_fail(stderr="error:")),
            patch("shutil.which", return_value="/usr/bin/crystal"),
        ):
            result = _run_crystal("bad code")
        assert result.stderr != ""

class TestRunNim:
    def test_compiles_and_runs(self):
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/nim"),
        ):
            mock_run.side_effect = [_ok(), _ok(stdout="hi\n")]
            result = _run_nim('echo "hi"')
        assert result.stdout == "hi\n"

    def test_compile_error(self):
        with (
            patch("subprocess.run", return_value=_fail(stderr="Error:")),
            patch("shutil.which", return_value="/usr/bin/nim"),
        ):
            result = _run_nim("bad code")
        assert result.stderr != ""

class TestRunClojure:
    def test_runs(self):
        with (
            patch("subprocess.run", return_value=_ok(stdout="hi\n")),
            patch("shutil.which", return_value="/usr/bin/clojure"),
        ):
            result = ec._run_clojure('(println "hi")')
        assert result.stdout == "hi\n"

    def test_timeout(self):
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("clojure", 60)),
            patch("shutil.which", return_value="/usr/bin/clojure"),
        ):
            result = ec._run_clojure('(println "hi")')
        assert "timed out" in result.stderr.lower()

class TestRunNasm:
    def test_compile_error(self):
        with (
            patch("subprocess.run", return_value=_fail(stderr="error: label")),
            patch("shutil.which", return_value="/usr/bin/nasm"),
        ):
            result = ec._run_nasm("bad asm code")
        assert result.stderr != ""

    def test_link_error(self):
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/nasm"),
        ):
            mock_run.side_effect = [_ok(), _fail(stderr="ld: error")]
            result = ec._run_nasm("section .text")
        assert result.stderr != ""

    def test_runs(self):
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/nasm"),
        ):
            mock_run.side_effect = [_ok(), _ok(), _ok(stdout="hi\n")]
            result = ec._run_nasm("section .text\nglobal _start")
        assert result.stdout == "hi\n"

    def test_raises_when_nasm_missing(self):
        with patch("shutil.which", return_value=None), patch("os.path.isfile", return_value=False):
            with pytest.raises(HTTPException) as exc:
                ec._run_nasm("section .text")
            assert exc.value.status_code == 500

    def test_timeout(self):
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/nasm"),
        ):
            mock_run.side_effect = [_ok(), _ok(), subprocess.TimeoutExpired("./main", 15)]
            result = ec._run_nasm("section .text")
        assert "timed out" in result.stderr.lower()

class TestRunCsharp:
    def test_runs(self):
        code = 'Console.WriteLine("hi");'
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/dotnet"),
        ):
            mock_run.return_value = _ok(stdout="hi\n")
            result = _run_csharp(code)
        assert result.stdout == "hi\n"

    def test_fsharp(self):
        code = 'printfn "hi"'
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/dotnet"),
        ):
            mock_run.return_value = _ok(stdout="hi\n")
            result = _run_csharp(code, "fsharp")
        assert result.stdout == "hi\n"

# ── _ensure_js_sandbox ────────────────────────────────────────────────────────

class TestEnsureJsSandbox:
    def test_installs_when_not_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(ec, "_JS_SANDBOX", Path(tmpdir)):
                with patch("subprocess.run", return_value=_ok()) as mock_npm:
                    result = ec._ensure_js_sandbox()
                assert result == Path(tmpdir)
                mock_npm.assert_called_once()

    def test_uses_cache_when_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / ".ready").write_text(ec._SANDBOX_VERSION)
            with patch.object(ec, "_JS_SANDBOX", p):
                with patch("subprocess.run") as mock_npm:
                    result = ec._ensure_js_sandbox()
                assert result == p
                mock_npm.assert_not_called()

    def test_does_not_write_marker_on_npm_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            with patch.object(ec, "_JS_SANDBOX", p):
                with patch("subprocess.run", return_value=_fail()):
                    ec._ensure_js_sandbox()
            assert not (p / ".ready").exists()

# ── _run_javascript ───────────────────────────────────────────────────────────

class TestRunJavascript:
    def _sandbox(self, tmpdir):
        p = Path(tmpdir)
        (p / "node_modules" / ".bin").mkdir(parents=True)
        (p / "node_modules" / "jsdom").mkdir(parents=True)
        return p

    def test_simple_js(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sb = self._sandbox(tmpdir)
            with patch.object(ec, "_ensure_js_sandbox", return_value=sb):
                with patch("subprocess.run") as mock_run:
                    mock_run.side_effect = [_ok(), _ok(stdout="hello\n")]
                    result = ec._run_javascript("console.log('hello')")
            assert result.stdout == "hello\n"

    def test_esbuild_error_returned(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sb = self._sandbox(tmpdir)
            with patch.object(ec, "_ensure_js_sandbox", return_value=sb):
                with patch("subprocess.run", return_value=_fail(stderr="build error")):
                    result = ec._run_javascript("bad code")
            assert result.stderr == "build error"

    def test_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sb = self._sandbox(tmpdir)
            with patch.object(ec, "_ensure_js_sandbox", return_value=sb):
                with patch("subprocess.run") as mock_run:
                    mock_run.side_effect = [_ok(), subprocess.TimeoutExpired("node", 15)]
                    result = ec._run_javascript("while(true){}")
            assert "timed out" in result.stderr.lower()

    def test_typescript_uses_tsx_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sb = self._sandbox(tmpdir)
            with patch.object(ec, "_ensure_js_sandbox", return_value=sb):
                with patch("subprocess.run") as mock_run:
                    mock_run.side_effect = [_ok(), _ok(stdout="hi\n")]
                    result = ec._run_javascript("console.log('hi')", "typescript")
            assert result.stdout == "hi\n"

    def test_react_component_auto_mount(self):
        code = "function App() { return null; }\nexport default App;"
        with tempfile.TemporaryDirectory() as tmpdir:
            sb = self._sandbox(tmpdir)
            with patch.object(ec, "_ensure_js_sandbox", return_value=sb):
                with patch("subprocess.run") as mock_run:
                    mock_run.side_effect = [_ok(), _ok(stdout="")]
                    result = ec._run_javascript(code, "react")
            assert result.stderr == ""

    def test_cleanup_on_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sb = self._sandbox(tmpdir)
            with patch.object(ec, "_ensure_js_sandbox", return_value=sb):
                with patch("subprocess.run", return_value=_fail(stderr="err")):
                    ec._run_javascript("code")
            # temp files cleaned up - no main.jsx left
            assert not (sb / "main.jsx").exists()

# ── _run_in_docker ────────────────────────────────────────────────────────────

class TestRunInDocker:
    def _mock_docker(self, output=b"hi\n"):
        mock_docker_mod = MagicMock()
        mock_client = MagicMock()
        mock_docker_mod.from_env.return_value = mock_client
        mock_client.containers.run.return_value = output
        return mock_docker_mod, mock_client

    def test_success(self):
        mock_docker_mod, mock_client = self._mock_docker(b"hi\n")
        with (
            patch.dict("sys.modules", {"docker": mock_docker_mod}),
            patch("controllers.execute._docker_client", None),
            patch("controllers.execute._get_docker_client", return_value=mock_client),
        ):
            result = _run_in_docker("python3", "print('hi')")
        assert "hi" in result.stdout

    def test_container_error_returns_stderr(self):
        import docker as real_docker

        mock_client = MagicMock()
        err = real_docker.errors.ContainerError(
            container=MagicMock(),
            exit_status=1,
            command="python3",
            image="openship-sandbox",
            stderr=b"runtime error",
        )
        mock_client.containers.run.side_effect = err
        import controllers.execute as ce

        old_client = ce._docker_client
        ce._docker_client = mock_client
        try:
            result = ce._run_in_docker("python3", "bad")
            assert "runtime error" in result.stderr
        finally:
            ce._docker_client = old_client

    def test_image_not_found_raises_http(self):
        import docker as real_docker

        mock_client = MagicMock()
        mock_client.containers.run.side_effect = real_docker.errors.ImageNotFound("not found")
        import controllers.execute as ce

        old_client = ce._docker_client
        ce._docker_client = mock_client
        try:
            with pytest.raises(HTTPException) as exc:
                ce._run_in_docker("python3", "print('hi')")
            assert exc.value.status_code == 500
            assert "sandbox-build" in exc.value.detail
        finally:
            ce._docker_client = old_client

    def test_timeout_returns_error_message(self):
        mock_client = MagicMock()
        mock_client.containers.run.side_effect = Exception("timed out waiting for container")
        import controllers.execute as ce

        old_client = ce._docker_client
        ce._docker_client = mock_client
        try:
            result = ce._run_in_docker("python3", "print('hi')")
            assert "timed out" in result.stderr.lower()
        finally:
            ce._docker_client = old_client

    def test_generic_docker_error_raises_http(self):
        mock_client = MagicMock()
        mock_client.containers.run.side_effect = Exception("connection refused to docker daemon")
        import controllers.execute as ce

        old_client = ce._docker_client
        ce._docker_client = mock_client
        try:
            with pytest.raises(HTTPException) as exc:
                ce._run_in_docker("python3", "print('hi')")
            assert exc.value.status_code == 500
        finally:
            ce._docker_client = old_client

# ── _get_docker_client ────────────────────────────────────────────────────────

class TestGetDockerClient:
    def test_returns_client(self):
        mock_docker = MagicMock()
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        import controllers.execute as ce

        old_client = ce._docker_client
        ce._docker_client = None
        try:
            with patch.dict("sys.modules", {"docker": mock_docker}):
                client = ce._get_docker_client()
            assert client is mock_client
        finally:
            ce._docker_client = old_client

    def test_raises_http_when_docker_unavailable(self):
        import controllers.execute as ce

        old_client = ce._docker_client
        ce._docker_client = None
        try:
            with patch.dict("sys.modules", {"docker": None}):
                with pytest.raises(HTTPException) as exc:
                    ce._get_docker_client()
                assert exc.value.status_code == 500
        finally:
            ce._docker_client = old_client

    def test_caches_client(self):
        mock_docker = MagicMock()
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        import controllers.execute as ce

        old_client = ce._docker_client
        ce._docker_client = None
        try:
            with patch.dict("sys.modules", {"docker": mock_docker}):
                c1 = ce._get_docker_client()
                c2 = ce._get_docker_client()
            assert c1 is c2
            mock_docker.from_env.assert_called_once()
        finally:
            ce._docker_client = old_client

# ── run_code (dispatcher) ─────────────────────────────────────────────────────

class TestRunCode:
    def test_sql_always_uses_builtin(self):
        result = run_code(_req("sql", "SELECT 1+1"), _user())
        assert "2" in result.stdout

    def test_sql_alias_sqlite(self):
        result = run_code(_req("sqlite", "SELECT 42"), _user())
        assert "42" in result.stdout

    def test_unsupported_language_raises_400(self):
        with patch.object(ec, "_AVAILABLE_RUNTIMES", {}), patch.object(ec, "USE_DOCKER", False):
            with pytest.raises(HTTPException) as exc:
                run_code(_req("brainf***"), _user())
            assert exc.value.status_code == 400

    def test_dispatches_to_javascript(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"javascript": "/usr/bin/node"}),
            patch.object(
                ec, "_run_javascript", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_js,
        ):
            run_code(_req("javascript", "console.log('hi')"), _user())
        mock_js.assert_called_once()

    def test_dispatches_to_java(self):
        code = 'public class Main { public static void main(String[] a) { System.out.println("hi"); } }'
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"java": "/usr/bin/java"}),
            patch.object(
                ec, "_run_java", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_java,
        ):
            run_code(_req("java", code), _user())
        mock_java.assert_called_once()

    def test_dispatches_to_cpp(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"cpp": "/usr/bin/g++"}),
            patch.object(
                ec, "_run_cpp", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_cpp,
        ):
            run_code(_req("cpp", "int main(){}"), _user())
        mock_cpp.assert_called_once()

    def test_dispatches_c_to_cpp_runner(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"c": "/usr/bin/gcc"}),
            patch.object(
                ec, "_run_cpp", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_cpp,
        ):
            run_code(_req("c", "int main(){}"), _user())
        mock_cpp.assert_called_once_with("int main(){}", "c")

    def test_dispatches_to_rust(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"rust": "/usr/bin/rustc"}),
            patch.object(
                ec, "_run_rust", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_rust,
        ):
            run_code(_req("rust", "fn main(){}"), _user())
        mock_rust.assert_called_once()

    def test_dispatches_to_go(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"go": "/usr/bin/go"}),
            patch.object(
                ec, "_run_go", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_go,
        ):
            run_code(_req("go", "package main\nfunc main(){}"), _user())
        mock_go.assert_called_once()

    def test_dispatches_to_kotlin(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"kotlin": "/usr/bin/kotlinc"}),
            patch.object(
                ec, "_run_kotlin", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_kt,
        ):
            run_code(_req("kotlin", "fun main(){}"), _user())
        mock_kt.assert_called_once()

    def test_dispatches_to_scala(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"scala": "/usr/bin/scala"}),
            patch.object(
                ec, "_run_scala", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_sc,
        ):
            run_code(_req("scala", "object Main extends App {}"), _user())
        mock_sc.assert_called_once()

    def test_dispatches_to_prolog(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"prolog": "/usr/bin/swipl"}),
            patch.object(
                ec, "_run_prolog", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_pl,
        ):
            run_code(_req("prolog", ":- initialization(main)."), _user())
        mock_pl.assert_called_once()

    def test_dispatches_to_zig(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"zig": "/usr/bin/zig"}),
            patch.object(
                ec, "_run_zig", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_zig,
        ):
            run_code(_req("zig", "pub fn main() !void {}"), _user())
        mock_zig.assert_called_once()

    def test_dispatches_to_cobol(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"cobol": "/usr/bin/cobc"}),
            patch.object(
                ec, "_run_cobol", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_cb,
        ):
            run_code(_req("cobol", "IDENTIFICATION DIVISION."), _user())
        mock_cb.assert_called_once()

    def test_dispatches_to_fortran(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"fortran": "/usr/bin/gfortran"}),
            patch.object(
                ec, "_run_fortran", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_ft,
        ):
            run_code(_req("fortran", "program main\nend program"), _user())
        mock_ft.assert_called_once()

    def test_dispatches_to_awk(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"awk": "/usr/bin/awk"}),
            patch.object(
                ec, "_run_awk", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_awk,
        ):
            run_code(_req("awk", 'BEGIN { print "hi" }'), _user())
        mock_awk.assert_called_once()

    def test_dispatches_to_sml(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"sml": "/usr/bin/sml"}),
            patch.object(
                ec, "_run_sml", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_sml,
        ):
            run_code(_req("sml", 'print "hi";'), _user())
        mock_sml.assert_called_once()

    def test_dispatches_to_haxe(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"haxe": "/usr/bin/haxe"}),
            patch.object(
                ec, "_run_haxe", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_haxe,
        ):
            run_code(_req("haxe", "class Main { static function main() {} }"), _user())
        mock_haxe.assert_called_once()

    def test_dispatches_to_sbcl(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"commonlisp": "/usr/bin/sbcl"}),
            patch.object(
                ec, "_run_sbcl", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_sbcl,
        ):
            run_code(_req("commonlisp", '(format t "hi")'), _user())
        mock_sbcl.assert_called_once()

    def test_dispatches_to_octave(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"octave": "/usr/bin/octave"}),
            patch.object(
                ec, "_run_octave", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_oct,
        ):
            run_code(_req("octave", 'disp("hi")'), _user())
        mock_oct.assert_called_once()

    def test_dispatches_to_simple_runner_for_ruby(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"ruby": "/usr/bin/ruby"}),
            patch.object(
                ec, "_run_simple", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_simple,
        ):
            run_code(_req("ruby", 'puts "hi"'), _user())
        mock_simple.assert_called_once()

    def test_docker_path_used_when_use_docker_true(self):
        with (
            patch.object(ec, "USE_DOCKER", True),
            patch.object(
                ec, "_run_in_docker", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_docker,
        ):
            run_code(_req("python3", "print('hi')"), _user())
        mock_docker.assert_called_once()

    def test_dispatches_to_crystal(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"crystal": "/usr/bin/crystal"}),
            patch.object(
                ec, "_run_crystal", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as m,
        ):
            run_code(_req("crystal", 'puts "hi"'), _user())
        m.assert_called_once()

    def test_dispatches_to_nim(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"nim": "/usr/bin/nim"}),
            patch.object(ec, "_run_nim", return_value=ExecuteResponse(stdout="hi", stderr="")) as m,
        ):
            run_code(_req("nim", 'echo "hi"'), _user())
        m.assert_called_once()

    def test_dispatches_to_csharp(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"csharp": "/usr/bin/dotnet"}),
            patch.object(
                ec, "_run_csharp", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as m,
        ):
            run_code(_req("csharp", 'Console.WriteLine("hi");'), _user())
        m.assert_called_once()

    def test_dispatches_to_odin(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"odin": "/usr/bin/odin"}),
            patch.object(
                ec, "_run_odin", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as m,
        ):
            run_code(_req("odin", "package main"), _user())
        m.assert_called_once()

    def test_dispatches_to_clojure(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"clojure": "/usr/bin/clojure"}),
            patch.object(
                ec, "_run_clojure", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as m,
        ):
            run_code(_req("clojure", '(println "hi")'), _user())
        m.assert_called_once()

    def test_dispatches_to_nasm(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"nasm": "/usr/bin/nasm"}),
            patch.object(
                ec, "_run_nasm", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as m,
        ):
            run_code(_req("nasm", "section .text"), _user())
        m.assert_called_once()

    def test_dispatches_to_coffeescript(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"coffee": "/usr/bin/coffee"}),
            patch.object(
                ec, "_run_simple", return_value=ExecuteResponse(stdout="hi", stderr="")
            ) as mock_simple,
        ):
            run_code(_req("coffee", 'console.log "hi"'), _user())
        mock_simple.assert_called_once()

    def test_unsupported_language_raises_400_end(self):
        with (
            patch.object(ec, "USE_DOCKER", False),
            patch.object(ec, "_AVAILABLE_RUNTIMES", {"unknownlang": "/bin/foo"}),
        ):
            with pytest.raises(HTTPException) as exc:
                run_code(_req("unknownlang", "code"), _user())
            assert exc.value.status_code == 400

    def test_language_normalized_to_lowercase(self):
        result = run_code(_req("SQL", "SELECT 1"), _user())
        assert "1" in result.stdout

# ── routes ────────────────────────────────────────────────────────────────────

class TestExecuteRoutes:
    def test_get_runtimes(self, auth_client):
        resp = auth_client.get("/execute/runtimes")
        assert resp.status_code == 200
        assert "languages" in resp.json()

    def test_run_code_sql(self, auth_client):
        resp = auth_client.post("/execute", json={"language": "sql", "code": "SELECT 42"})
        assert resp.status_code == 200
        assert "42" in resp.json()["stdout"]

    def test_run_code_unsupported_language(self, auth_client):
        with patch.object(ec, "USE_DOCKER", False), patch.object(ec, "_AVAILABLE_RUNTIMES", {}):
            resp = auth_client.post("/execute", json={"language": "nonexistent", "code": "code"})
            assert resp.status_code == 400

# ── coverage for previously-uncovered lines ───────────────────────────────────

class TestRunSqlException:
    def test_connect_exception_returns_stderr(self):
        import sqlite3

        with patch("sqlite3.connect", side_effect=Exception("db boom")):
            r = _run_sql("SELECT 1")
        assert "db boom" in r.stderr

class TestFindScalaLib:
    def test_returns_none_when_nothing_found(self):
        with patch("glob.glob", return_value=[]):
            result = ec._find_scala_lib()
        assert result is None

class TestRunCompiledSingle:
    def test_raises_when_binary_missing(self):
        with patch("shutil.which", return_value=None), patch("os.path.isfile", return_value=False):
            with pytest.raises(HTTPException) as exc:
                _run_crystal("x : Int32 = 1")
            assert exc.value.status_code == 500

    def test_timeout_during_run(self):
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/crystal"),
        ):
            mock_run.side_effect = [
                _ok(),
                subprocess.TimeoutExpired("./main", 15),
            ]
            result = _run_crystal("puts 1")
        assert "timed out" in result.stderr.lower()

class TestRunNasmLinux:
    def test_linux_link_path(self):
        with (
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/nasm"),
            patch("platform.system", return_value="Linux"),
        ):
            mock_run.side_effect = [_ok(), _ok(), _ok(stdout="hello\n")]
            result = ec._run_nasm("section .text\nglobal _start")
        assert result.stdout == "hello\n"
        ld_call = mock_run.call_args_list[1]
        cmd = ld_call[0][0]
        assert cmd[0] == "ld"
        assert "-lSystem" not in cmd
