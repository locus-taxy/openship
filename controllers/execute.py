import re
import shutil
import subprocess
import sys
import sqlite3
import tempfile
import os
from pathlib import Path
from typing import Optional
from fastapi import HTTPException

from models.user import User
from schemas.execute import ExecuteRequest, ExecuteResponse

TIMEOUT_SECONDS = 15
TIMEOUT_JVM = 60  # Scala/Kotlin JVM startup is slow

# ── Docker sandbox ────────────────────────────────────────────────────────────

# Default to the isolated Docker sandbox path (fail closed for untrusted /execute code).
# Every supported deployment sets SANDBOX_USE_DOCKER explicitly; this default only governs
# unconfigured runs, which should not execute user code directly on the host.
USE_DOCKER = os.getenv("SANDBOX_USE_DOCKER", "true").lower() == "true"
DOCKER_IMAGE = os.getenv("SANDBOX_DOCKER_IMAGE", "openship-sandbox")

_docker_client = None

def _get_docker_client():
    global _docker_client
    if _docker_client is None:
        try:
            import docker

            _docker_client = docker.from_env()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Docker not available: {e}")
    return _docker_client

def _get_filename(lang: str) -> str:
    ext_map = {
        "python": "main.py",
        "python3": "main.py",
        "javascript": "main.jsx",
        "js": "main.jsx",
        "jsx": "main.jsx",
        "typescript": "main.tsx",
        "ts": "main.tsx",
        "tsx": "main.tsx",
        "react": "main.jsx",
        "vue": "main.jsx",
        "node": "main.js",
        "nodejs": "main.js",
        "next": "main.jsx",
        "nextjs": "main.jsx",
        "angular": "main.ts",
        "express": "main.js",
        "deno": "main.ts",
        "ruby": "main.rb",
        "rb": "main.rb",
        "bash": "main.sh",
        "sh": "main.sh",
        "shell": "main.sh",
        "perl": "main.pl",
        "pl": "main.pl",
        "lua": "main.lua",
        "php": "main.php",
        "elixir": "main.ex",
        "ex": "main.ex",
        "exs": "main.exs",
        "erlang": "main.erl",
        "erl": "main.erl",
        "julia": "main.jl",
        "jl": "main.jl",
        "r": "main.r",
        "rscript": "main.r",
        "haskell": "main.hs",
        "hs": "main.hs",
        "ocaml": "main.ml",
        "ml": "main.ml",
        "racket": "main.rkt",
        "rkt": "main.rkt",
        "scheme": "main.rkt",
        "lisp": "main.rkt",
        "tcl": "main.tcl",
        "awk": "main.awk",
        "groovy": "main.groovy",
        "powershell": "main.ps1",
        "pwsh": "main.ps1",
        "ps1": "main.ps1",
        "commonlisp": "main.lisp",
        "cl": "main.lisp",
        "lisp2": "main.lisp",
        "sml": "main.sml",
        "standardml": "main.sml",
        "prolog": "main.pl",
        "pl2": "main.pl",
        "octave": "main.m",
        "matlab": "main.m",
        "dart": "main.dart",
        "flutter": "main.dart",
        "java": "Main.java",
        "cpp": "main.cpp",
        "c++": "main.cpp",
        "cxx": "main.cpp",
        "cc": "main.cpp",
        "c": "main.c",
        "go": "main.go",
        "golang": "main.go",
        "rust": "main.rs",
        "rs": "main.rs",
        "swift": "main.swift",
        "kotlin": "main.kt",
        "kt": "main.kt",
        "scala": "main.scala",
        "crystal": "main.cr",
        "cr": "main.cr",
        "nim": "main.nim",
        "zig": "main.zig",
        "csharp": "main.cs",
        "cs": "main.cs",
        "c#": "main.cs",
        "fsharp": "main.fs",
        "fs": "main.fs",
        "f#": "main.fs",
        "fortran": "main.f90",
        "f90": "main.f90",
        "f95": "main.f90",
        "f77": "main.f90",
        "cobol": "main.cob",
        "cob": "main.cob",
        "cbl": "main.cob",
        "odin": "main.odin",
        "haxe": "main.hx",
        "hx": "main.hx",
        "clojure": "main.clj",
        "clj": "main.clj",
        "coffeescript": "main.coffee",
        "coffee": "main.coffee",
        "nasm": "main.asm",
        "asm": "main.asm",
        "assembly": "main.asm",
        "fish": "main.fish",
        "raku": "main.raku",
        "perl6": "main.raku",
        "guile": "main.scm",
        "d": "main.d",
        "dlang": "main.d",
        "vala": "main.vala",
        "pascal": "main.pas",
        "pas": "main.pas",
        "ada": "main.adb",
        "adb": "main.adb",
        "zsh": "main.zsh",
        "ksh": "main.ksh",
        "tcsh": "main.tcsh",
        "csh": "main.tcsh",
        "luajit": "main.lua",
        "clisp": "main.lisp",
        "newlisp": "main.lsp",
        "rexx": "main.rexx",
        "expect": "main.exp",
        "m4": "main.m4",
        "gambit": "main.scm",
        "pike": "main.pike",
        "yabasic": "main.bas",
        "basic": "main.bas",
        "algol68": "main.a68",
        "a68": "main.a68",
        "forth": "main.fth",
        "fth": "main.fth",
        "chicken": "main.scm",
        "chickenscheme": "main.scm",
        "objc": "main.m",
        "objective-c": "main.m",
        "objectivec": "main.m",
        "v": "main.v",
        "vlang": "main.v",
    }
    return ext_map.get(lang, "main.txt")

def _run_in_docker(lang: str, code: str) -> ExecuteResponse:
    import docker as docker_lib

    filename = _get_filename(lang)
    client = _get_docker_client()

    with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
        code_file = os.path.join(tmpdir, filename)
        with open(code_file, "w") as f:
            f.write(code)
        # The sandbox image runs as a non-root user; make the bind mount writable
        # so it can emit compiled binaries/intermediates into /sandbox.
        os.chmod(tmpdir, 0o777)

        container = None
        try:
            container = client.containers.run(
                image=DOCKER_IMAGE,
                command=[lang, f"/sandbox/{filename}"],
                volumes={tmpdir: {"bind": "/sandbox", "mode": "rw"}},
                network_disabled=True,
                mem_limit="256m",
                nano_cpus=500_000_000,  # 0.5 CPU
                stdout=True,
                stderr=True,
                detach=True,
            )
            try:
                result = container.wait(timeout=TIMEOUT_JVM)
            except Exception:
                container.kill()
                return ExecuteResponse(
                    stdout="", stderr=f"Execution timed out after {TIMEOUT_JVM}s."
                )

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            exit_code = result.get("StatusCode", 0)
            if exit_code != 0 and not stderr:
                stderr = f"Process exited with code {exit_code}"
            return ExecuteResponse(stdout=stdout, stderr=stderr)
        except docker_lib.errors.ImageNotFound:
            raise HTTPException(
                status_code=500,
                detail="Sandbox image not found. Run `make sandbox-build` first.",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Docker execution failed: {e}")
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

# ── Persistent JS sandbox (esbuild + react + jsdom, installed once) ───────────

_JS_SANDBOX = Path(
    os.getenv("OPENSHIP_JS_SANDBOX_PATH", str(Path(tempfile.gettempdir()) / "openship_js_sandbox"))
)
_SANDBOX_VERSION = "3"

def _ensure_js_sandbox() -> Path:
    marker = _JS_SANDBOX / ".ready"
    if marker.exists() and marker.read_text().strip() == _SANDBOX_VERSION:
        return _JS_SANDBOX
    _JS_SANDBOX.mkdir(exist_ok=True)
    # jsdom is pinned to 22.x: jsdom >=24 pulls an ESM-only html-encoding-sniffer
    # that breaks under Node 18 + esbuild CJS bundling.
    (_JS_SANDBOX / "package.json").write_text(
        '{"dependencies":{"react":"^18","react-dom":"^18","esbuild":"latest","jsdom":"22.1.0"}}'
    )
    result = subprocess.run(
        ["npm", "install", "--silent", "--no-audit", "--no-fund"],
        cwd=str(_JS_SANDBOX),
        capture_output=True,
        timeout=180,
    )
    if result.returncode != 0:
        err = result.stderr
        if isinstance(err, bytes):
            err = err.decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=500,
            detail=f"JS sandbox bootstrap failed (npm install): {(err or '').strip()[:500] or 'unknown error'}",
        )
    marker.write_text(_SANDBOX_VERSION)
    return _JS_SANDBOX

# ── Runtime detection ─────────────────────────────────────────────────────────
#
# Maps each canonical language name to:
#   - the binary to look for (via shutil.which)
#   - the set of language tags that use it

_RUNTIME_SPECS = [
    # (canonical_name, [binary candidates], [language tags that map to it])
    ("python", ["python3", "python"], ["python", "python3"]),
    (
        "node",
        ["node", "nodejs"],
        [
            "javascript",
            "js",
            "jsx",
            "tsx",
            "typescript",
            "ts",
            "react",
            "vue",
            "node",
            "nodejs",
            "next",
            "nextjs",
            "angular",
            "express",
        ],
    ),
    ("ruby", ["ruby"], ["ruby", "rb"]),
    ("bash", ["bash"], ["bash", "sh", "shell"]),
    ("swift", ["swift"], ["swift"]),
    ("go", ["go"], ["go", "golang"]),
    ("rustc", ["rustc"], ["rust", "rs"]),
    ("java", ["java"], ["java"]),
    ("cpp", ["g++", "clang++"], ["cpp", "c++", "cxx", "cc"]),
    ("gcc", ["gcc", "clang"], ["c"]),
    ("php", ["php"], ["php"]),
    ("kotlinc", ["kotlinc"], ["kotlin", "kt"]),
    ("dart", ["dart"], ["dart", "flutter"]),
    ("scala", ["scalac", "scala"], ["scala"]),
    ("perl", ["perl"], ["perl", "pl"]),
    ("lua", ["lua", "lua5.4", "lua5.3", "lua5.5"], ["lua"]),
    ("elixir", ["elixir"], ["elixir", "ex", "exs"]),
    ("julia", ["julia"], ["julia", "jl"]),
    ("Rscript", ["Rscript"], ["r", "rscript"]),
    ("groovy", ["groovy"], ["groovy"]),
    ("pwsh", ["pwsh", "powershell"], ["powershell", "pwsh", "ps1"]),
    ("fish", ["fish"], ["fish"]),
    ("runghc", ["runghc", "runhaskell"], ["haskell", "hs"]),
    ("dotnet", ["dotnet"], ["csharp", "cs", "c#", "fsharp", "fs", "f#"]),
    ("crystal", ["crystal"], ["crystal", "cr"]),
    ("ocaml", ["ocaml"], ["ocaml", "ml"]),
    ("racket", ["racket"], ["racket", "rkt", "scheme", "lisp"]),
    ("nim", ["nim"], ["nim"]),
    ("zig", ["zig"], ["zig"]),
    ("deno", ["deno"], ["deno"]),
    ("escript", ["escript"], ["erlang", "erl"]),
    ("octave", ["octave-cli", "octave"], ["octave", "matlab"]),
    ("swipl", ["swipl"], ["prolog", "pl2"]),
    ("odin", ["odin"], ["odin"]),
    ("cobc", ["cobc"], ["cobol", "cob", "cbl"]),
    ("sbcl", ["sbcl"], ["commonlisp", "common-lisp", "cl", "lisp2"]),
    ("sml", ["sml", "poly"], ["sml", "standardml"]),
    ("tclsh", ["tclsh", "tclsh9.0"], ["tcl"]),
    ("awk", ["awk", "gawk"], ["awk"]),
    ("gfortran", ["gfortran"], ["fortran", "f90", "f95", "f77"]),
    ("haxe", ["haxe"], ["haxe", "hx"]),
    ("clojure", ["clojure"], ["clojure", "clj"]),
    ("coffee", ["coffee"], ["coffeescript", "coffee"]),
    ("nasm", ["nasm"], ["nasm", "asm", "assembly"]),
    ("raku", ["raku", "perl6"], ["raku", "perl6"]),
    ("guile", ["guile", "guile-3.0"], ["guile"]),
    ("gdc", ["gdc"], ["d", "dlang"]),
    ("valac", ["valac"], ["vala"]),
    ("fpc", ["fpc"], ["pascal", "pas"]),
    ("gnatmake", ["gnatmake"], ["ada", "adb"]),
    # ── Extended batch ──
    ("zsh", ["zsh"], ["zsh"]),
    ("ksh", ["ksh"], ["ksh"]),
    ("tcsh", ["tcsh"], ["tcsh", "csh"]),
    ("luajit", ["luajit"], ["luajit"]),
    ("clisp", ["clisp"], ["clisp"]),
    ("newlisp", ["newlisp"], ["newlisp"]),
    ("regina", ["regina", "rexx"], ["rexx"]),
    ("expect", ["expect"], ["expect"]),
    ("m4", ["m4"], ["m4"]),
    ("gsi", ["gsi"], ["gambit"]),
    ("pike", ["pike", "pike8.0"], ["pike"]),
    ("yabasic", ["yabasic"], ["yabasic", "basic"]),
    ("a68g", ["a68g"], ["algol68", "a68"]),
    ("gforth", ["gforth"], ["forth", "fth"]),
    ("csi", ["chicken-csi", "csi"], ["chicken", "chickenscheme"]),
    ("objc", ["gcc", "clang"], ["objc", "objective-c", "objectivec"]),
    ("v", ["v"], ["v", "vlang"]),
    ("sqlite3", [None], ["sql", "sqlite"]),
]

# Extra directories to search beyond PATH (e.g. Homebrew on macOS)
_EXTRA_DIRS = ["/opt/homebrew/bin", "/usr/local/bin", os.path.expanduser("~/.cargo/bin")]

def _find_binary(candidates: list) -> Optional[str]:
    """Find first available binary from candidates list, checking PATH + extra dirs."""
    for binary in candidates:
        if binary is None:
            return "builtin"
        found = shutil.which(binary)
        if found:
            return found
        for d in _EXTRA_DIRS:
            full = os.path.join(d, binary)
            if os.path.isfile(full) and os.access(full, os.X_OK):
                return full
    return None

def _find_scala_lib() -> Optional[str]:
    import glob

    patterns = [
        "/opt/homebrew/Cellar/scala/*/libexec/maven2/org/scala-lang/scala-library/*/scala-library-*.jar",
        "/usr/local/share/scala/lib/scala-library.jar",
        "/usr/share/scala/lib/scala-library.jar",
        "/opt/scala/lib/scala-library.jar",
        "/opt/scala/lib/scala-library*.jar",
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return None

# JVM languages need their full toolchain, not just one binary. Each tag is only
# advertised if every predicate holds (avoids false positives in /execute/runtimes).
def _java_ok() -> bool:
    return bool(_find_binary(["javac"]) and _find_binary(["java"]))

def _kotlin_ok() -> bool:
    return bool(_find_binary(["kotlinc"]) and _find_binary(["java"]))

def _scala_ok() -> bool:
    return bool(_find_binary(["scalac"]) and _find_binary(["java"]) and _find_scala_lib())

_TOOLCHAIN_GATES = {
    "java": _java_ok,
    "kotlin": _kotlin_ok,
    "kt": _kotlin_ok,
    "scala": _scala_ok,
}

def _detect_runtimes() -> dict[str, str]:
    """Return {language_tag: binary_path} for every available runtime."""
    available: dict[str, str] = {}
    for canonical, candidates, tags in _RUNTIME_SPECS:
        path = _find_binary(candidates)
        if not path:
            continue
        for tag in tags:
            available[tag] = path
    # Drop JVM languages whose full toolchain (compiler + runtime + libs) is missing.
    for tag, gate in _TOOLCHAIN_GATES.items():
        if tag in available and not gate():
            del available[tag]
    return available

# Detected once at import time; cached for the process lifetime
_AVAILABLE_RUNTIMES: dict[str, str] = _detect_runtimes()
SUPPORTED_LANGUAGES = sorted(_AVAILABLE_RUNTIMES.keys())

def get_available_runtimes() -> dict:
    """Return the list of runnable language tags for this server."""
    return {"languages": SUPPORTED_LANGUAGES}

# ── Language runners ──────────────────────────────────────────────────────────

_JS_LANGS = {
    "javascript",
    "js",
    "jsx",
    "tsx",
    "typescript",
    "ts",
    "react",
    "vue",
    "node",
    "nodejs",
    "next",
    "nextjs",
    "angular",
    "express",
}
# Only SQLite-compatible dialects: _run_sql() executes against sqlite3 in-memory.
_SQL_LANGS = {"sql", "sqlite"}
_JAVA_LANGS = {"java"}
_CPP_LANGS = {"cpp", "c++", "cxx", "cc"}
_C_LANGS = {"c"}
_COMPILED_LANGS = _JAVA_LANGS | _CPP_LANGS | _C_LANGS

_SIMPLE_RUNNERS: dict[str, tuple[str, str]] = {
    # lang_tag: (binary_name, file_extension)
    "python": ("python3", ".py"),
    "python3": ("python3", ".py"),
    "ruby": ("ruby", ".rb"),
    "rb": ("ruby", ".rb"),
    "bash": ("bash", ".sh"),
    "sh": ("bash", ".sh"),
    "shell": ("bash", ".sh"),
    "swift": ("swift", ".swift"),
    "go": ("go", ".go"),
    "golang": ("go", ".go"),
    "rust": ("rustc", ".rs"),
    "rs": ("rustc", ".rs"),
    "php": ("php", ".php"),
    "perl": ("perl", ".pl"),
    "pl": ("perl", ".pl"),
    "lua": ("lua", ".lua"),
    "elixir": ("elixir", ".ex"),
    "ex": ("elixir", ".ex"),
    "exs": ("elixir", ".exs"),
    # scala handled by _run_scala
    "kotlin": ("kotlinc", ".kt"),
    "kt": ("kotlinc", ".kt"),
    "dart": ("dart", ".dart"),
    "flutter": ("dart", ".dart"),
    "julia": ("julia", ".jl"),
    "jl": ("julia", ".jl"),
    "r": ("Rscript", ".r"),
    "rscript": ("Rscript", ".r"),
    "groovy": ("groovy", ".groovy"),
    "powershell": ("pwsh", ".ps1"),
    "pwsh": ("pwsh", ".ps1"),
    "ps1": ("pwsh", ".ps1"),
    "fish": ("fish", ".fish"),
    "haskell": ("runghc", ".hs"),
    "hs": ("runghc", ".hs"),
    "racket": ("racket", ".rkt"),
    "rkt": ("racket", ".rkt"),
    "scheme": ("racket", ".rkt"),
    "lisp": ("racket", ".rkt"),
    "ocaml": ("ocaml", ".ml"),
    "ml": ("ocaml", ".ml"),
    "erlang": ("escript", ".erl"),
    "erl": ("escript", ".erl"),
    "deno": ("deno", ".ts"),
    "octave": ("octave-cli", ".m"),
    "matlab": ("octave-cli", ".m"),
    "commonlisp": ("sbcl", ".lisp"),
    "common-lisp": ("sbcl", ".lisp"),
    "cl": ("sbcl", ".lisp"),
    "lisp2": ("sbcl", ".lisp"),
    "sml": ("sml", ".sml"),
    "standardml": ("sml", ".sml"),
    "tcl": ("tclsh", ".tcl"),
    "odin": ("odin", ".odin"),
    "haxe": ("haxe", ".hx"),
    "coffeescript": ("coffee", ".coffee"),
    "coffee": ("coffee", ".coffee"),
    "raku": ("raku", ".raku"),
    "perl6": ("raku", ".raku"),
    "guile": ("guile", ".scm"),
    "zsh": ("zsh", ".zsh"),
    "ksh": ("ksh", ".ksh"),
    "tcsh": ("tcsh", ".tcsh"),
    "csh": ("tcsh", ".tcsh"),
    "luajit": ("luajit", ".lua"),
    "clisp": ("clisp", ".lisp"),
    "newlisp": ("newlisp", ".lsp"),
    "rexx": ("regina", ".rexx"),
    "expect": ("expect", ".exp"),
    "m4": ("m4", ".m4"),
    "gambit": ("gsi", ".scm"),
    "pike": ("pike", ".pike"),
    "yabasic": ("yabasic", ".bas"),
    "basic": ("yabasic", ".bas"),
    "algol68": ("a68g", ".a68"),
    "a68": ("a68g", ".a68"),
    # cobol, prolog, fortran, awk handled by dedicated runners
    # crystal, nim, zig, csharp, clojure, nasm handled by dedicated runners
    # d, vala, pascal, ada handled by dedicated compiled runners
    # forth, chicken, objc, v handled by dedicated runners
}

def _run_javascript(code: str, lang: str = "javascript") -> ExecuteResponse:
    sandbox = _ensure_js_sandbox()
    esbuild = sandbox / "node_modules" / ".bin" / "esbuild"

    m = re.search(r"export\s+default\s+(\w+)", code)
    if m and "createRoot" not in code:
        component_name = m.group(1)
        react_import = (
            ""
            if ("from 'react'" in code or 'from "react"' in code)
            else "import React from 'react';\n"
        )
        reactdom_import = (
            "" if "react-dom" in code else "import ReactDOM from 'react-dom/client';\n"
        )
        code = (
            code.rstrip()
            + f"\n\n{react_import}{reactdom_import}"
            + f"ReactDOM.createRoot(document.getElementById('root')).render(React.createElement({component_name}));\n"
        )

    jsdom_setup = f"""\
const {{ JSDOM }} = require({str(sandbox / 'node_modules' / 'jsdom')!r});
const _dom = new JSDOM('<!DOCTYPE html><html><body><div id="root"></div></body></html>');
const _globals = {{
  window: _dom.window, document: _dom.window.document,
  navigator: _dom.window.navigator, location: _dom.window.location,
  HTMLElement: _dom.window.HTMLElement, Element: _dom.window.Element,
  Node: _dom.window.Node, Text: _dom.window.Text,
  Event: _dom.window.Event, CustomEvent: _dom.window.CustomEvent,
  requestAnimationFrame: (cb) => setTimeout(cb, 0),
  cancelAnimationFrame: clearTimeout,
}};
for (const [k, v] of Object.entries(_globals)) {{
  Object.defineProperty(global, k, {{ value: v, writable: true, configurable: true }});
}}
"""
    ext = ".tsx" if lang in ("typescript", "ts", "tsx") else ".jsx"
    with tempfile.TemporaryDirectory() as workdir:
        work = Path(workdir)
        src = work / f"main{ext}"
        out = work / "out.js"
        final = work / "run.js"
        src.write_text(code)
        bundle = subprocess.run(
            [
                str(esbuild),
                str(src),
                "--bundle",
                "--platform=node",
                "--format=cjs",
                f"--outfile={out}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(sandbox),
        )
        if bundle.returncode != 0:
            return ExecuteResponse(stdout="", stderr=bundle.stderr)
        run_script = f"""\
{jsdom_setup}
require({str(out)!r});
(async () => {{
  await new Promise(r => setTimeout(r, 50));
  const root = document.getElementById("root");
  if (root && root.innerHTML.trim()) {{
    console.log("\\n=== React Output ===");
    console.log(root.innerHTML);
  }}
}})();
"""
        final.write_text(run_script)
        try:
            result = subprocess.run(
                ["node", str(final)],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=str(sandbox),
            )
            return ExecuteResponse(stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_sql(code: str) -> ExecuteResponse:
    output_lines: list[str] = []
    try:
        conn = sqlite3.connect(":memory:")
        for stmt in [s.strip() for s in code.split(";") if s.strip()]:
            try:
                cur = conn.execute(stmt)
                rows = cur.fetchall()
                if rows:
                    if cur.description:
                        headers = [d[0] for d in cur.description]
                        output_lines.append(" | ".join(headers))
                        output_lines.append("-" * (sum(len(h) for h in headers) + 3 * len(headers)))
                    for row in rows:
                        output_lines.append(" | ".join(str(v) for v in row))
            except sqlite3.Error as e:
                output_lines.append(f"Error: {e}")
        conn.close()
    except Exception as e:
        return ExecuteResponse(stdout="", stderr=str(e))
    return ExecuteResponse(stdout="\n".join(output_lines), stderr="")

def _apply_autowrap(lang: str, code: str) -> str:
    """Apply language-specific entry-point wrapping so lesson snippets run correctly."""
    if lang in ("rust", "rs"):
        if "fn main()" not in code:
            fns = re.findall(r"fn\s+(\w+)\s*\(", code)
            calls = "\n    ".join(f"{fn}();" for fn in fns if fn != "main")
            code = code.rstrip() + f"\n\nfn main() {{\n    {calls}\n}}\n"

    elif lang in ("go", "golang"):
        if "package " not in code:
            code = 'package main\n\nimport "fmt"\n\n' + code
        if "func main()" not in code:
            fns = re.findall(r"func\s+(\w+)\s*\(", code)
            calls = "\n    ".join(f"{fn}()" for fn in fns if fn != "main")
            code = (
                code.rstrip()
                + f'\n\nfunc main() {{\n    {calls}\n    _ = fmt.Sprintf("") // suppress unused import\n}}\n'
            )

    elif lang in ("kotlin", "kt"):
        if "fun main(" not in code:
            fns = re.findall(r"fun\s+(\w+)\s*\(", code)
            calls = "\n    ".join(f"{fn}()" for fn in fns if fn != "main")
            code = code.rstrip() + f"\n\nfun main() {{\n    {calls}\n}}\n"

    elif lang in ("cpp", "c++", "cxx", "cc"):
        if "int main(" not in code and "int main (" not in code:
            fns = re.findall(r"(?:void|int|float|double|auto|std::\w+)\s+(\w+)\s*\(", code)
            calls = "\n    ".join(f"{fn}();" for fn in fns if fn not in ("main",))
            code = code.rstrip() + f"\n\nint main() {{\n    {calls}\n    return 0;\n}}\n"

    elif lang == "c":
        if "int main(" not in code and "int main (" not in code:
            fns = re.findall(r"(?:void|int|float|double|char\*?)\s+(\w+)\s*\(", code)
            calls = "\n    ".join(f"{fn}();" for fn in fns if fn not in ("main",))
            code = code.rstrip() + f"\n\nint main() {{\n    {calls}\n    return 0;\n}}\n"

    elif lang == "java":
        if "class " not in code:
            fns = re.findall(r"(?:public\s+)?static\s+\w+\s+(\w+)\s*\(\s*\)", code)
            calls = "\n        ".join(f"{fn}();" for fn in fns if fn != "main")
            code = f"public class Main {{\n    {code.strip()}\n\n    public static void main(String[] args) {{\n        {calls}\n    }}\n}}"
        elif "public static void main" not in code:
            fns = re.findall(r"(?:public\s+)?static\s+\w+\s+(\w+)\s*\(\s*\)", code)
            calls = "\n        ".join(f"{fn}();" for fn in fns if fn != "main")
            code = (
                code.rstrip().rstrip("}")
                + f"\n    public static void main(String[] args) {{\n        {calls}\n    }}\n}}"
            )

    elif lang in ("zig",):
        if "pub fn main" not in code:
            fns = re.findall(r"(?:pub\s+)?fn\s+(\w+)", code)
            calls = "\n    ".join(f"{fn}();" for fn in fns if fn != "main")
            code = code.rstrip() + f"\n\npub fn main() void {{\n    {calls}\n}}\n"

    # React auto-mount
    elif lang in _JS_LANGS:
        m = re.search(r"export\s+default\s+(\w+)", code)
        if m and "createRoot" not in code:
            component_name = m.group(1)
            react_import = (
                ""
                if ("from 'react'" in code or 'from "react"' in code)
                else "import React from 'react';\n"
            )
            reactdom_import = (
                "" if "react-dom" in code else "import ReactDOM from 'react-dom/client';\n"
            )
            code = (
                code.rstrip()
                + f"\n\n{react_import}{reactdom_import}"
                + f"ReactDOM.createRoot(document.getElementById('root')).render(React.createElement({component_name}));\n"
            )

    return code

def _run_java(code: str) -> ExecuteResponse:
    # Auto-wrap: if no class, embed snippet as class body and call no-arg static methods
    if "class " not in code:
        fns = re.findall(r"(?:public\s+)?static\s+\w+\s+(\w+)\s*\(\s*\)", code)
        calls = "\n        ".join(f"{fn}();" for fn in fns if fn != "main")
        code = f"public class Main {{\n    {code.strip()}\n\n    public static void main(String[] args) {{\n        {calls}\n    }}\n}}"
    elif "public static void main" not in code:
        fns = re.findall(r"(?:public\s+)?static\s+\w+\s+(\w+)\s*\(\s*\)", code)
        calls = "\n        ".join(f"{fn}();" for fn in fns if fn != "main")
        code = (
            code.rstrip().rstrip("}")
            + f"\n    public static void main(String[] args) {{\n        {calls}\n    }}\n}}"
        )
    m = re.search(r"public\s+class\s+(\w+)", code)
    class_name = m.group(1) if m else "Main"
    java = _find_binary(["java"]) or "java"
    javac = _find_binary(["javac"]) or "javac"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, f"{class_name}.java")
        with open(src, "w") as f:
            f.write(code)
        compile_result = subprocess.run(
            [javac, src],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tmpdir,
        )
        if compile_result.returncode != 0:
            return ExecuteResponse(stdout="", stderr=compile_result.stderr)
        try:
            run_result = subprocess.run(
                [java, class_name],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=run_result.stdout, stderr=run_result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_cpp(code: str, lang: str = "cpp") -> ExecuteResponse:
    # Auto-wrap: if no main(), call all top-level functions from a generated main
    if "int main(" not in code and "int main (" not in code:
        if lang == "c":
            fns = re.findall(r"(?:void|int|float|double|char\*?)\s+(\w+)\s*\(", code)
        else:
            fns = re.findall(r"(?:void|int|float|double|auto|std::\w+)\s+(\w+)\s*\(", code)
        calls = "\n    ".join(f"{fn}();" for fn in fns if fn not in ("main",))
        if lang == "c":
            code = code.rstrip() + f"\n\nint main() {{\n    {calls}\n    return 0;\n}}\n"
        else:
            code = code.rstrip() + f"\n\nint main() {{\n    {calls}\n    return 0;\n}}\n"

    compiler = _find_binary(["g++", "clang++"]) or "g++"
    if lang == "c":
        compiler = _find_binary(["gcc", "clang"]) or "gcc"
    ext = ".c" if lang == "c" else ".cpp"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, f"main{ext}")
        binary = os.path.join(tmpdir, "main")
        with open(src, "w") as f:
            f.write(code)
        std_flag = "-std=c11" if lang == "c" else "-std=c++17"
        compile_result = subprocess.run(
            [compiler, std_flag, src, "-o", binary],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if compile_result.returncode != 0:
            return ExecuteResponse(stdout="", stderr=compile_result.stderr)
        try:
            run_result = subprocess.run(
                [binary],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=run_result.stdout, stderr=run_result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_rust(code: str) -> ExecuteResponse:
    # Auto-wrap: if there's no main(), call all top-level fn definitions from a generated main
    if "fn main()" not in code:
        fns = re.findall(r"fn\s+(\w+)\s*\(", code)
        calls = "\n".join(f"    {fn}();" for fn in fns if fn != "main")
        code = code.rstrip() + f"\n\nfn main() {{\n{calls}\n}}\n"

    rustc = _find_binary(["rustc"]) or "rustc"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.rs")
        binary = os.path.join(tmpdir, "main")
        with open(src, "w") as f:
            f.write(code)
        compile_result = subprocess.run(
            [rustc, src, "-o", binary],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if compile_result.returncode != 0:
            return ExecuteResponse(stdout="", stderr=compile_result.stderr)
        try:
            run_result = subprocess.run(
                [binary],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=run_result.stdout, stderr=run_result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_go(code: str) -> ExecuteResponse:
    # Auto-wrap: add package main and func main() if missing
    if "package " not in code:
        code = 'package main\n\nimport "fmt"\n\n' + code
    if "func main()" not in code:
        fns = re.findall(r"func\s+(\w+)\s*\(", code)
        calls = "\n    ".join(f"{fn}()" for fn in fns if fn != "main")
        code = (
            code.rstrip()
            + f'\n\nfunc main() {{\n    {calls}\n    _ = fmt.Sprintf("") // suppress unused import\n}}\n'
        )

    go = _find_binary(["go"]) or "go"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.go")
        with open(src, "w") as f:
            f.write(code)
        try:
            result = subprocess.run(
                [go, "run", src],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_kotlin(code: str) -> ExecuteResponse:
    # Auto-wrap: if no main(), call all top-level functions from a generated main
    if "fun main(" not in code:
        fns = re.findall(r"fun\s+(\w+)\s*\(", code)
        calls = "\n    ".join(f"{fn}()" for fn in fns if fn != "main")
        code = code.rstrip() + f"\n\nfun main() {{\n    {calls}\n}}\n"

    kotlinc = _find_binary(["kotlinc"]) or "kotlinc"
    java = _find_binary(["java"]) or "java"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.kt")
        jar = os.path.join(tmpdir, "main.jar")
        with open(src, "w") as f:
            f.write(code)
        compile_result = subprocess.run(
            [kotlinc, src, "-include-runtime", "-d", jar],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if compile_result.returncode != 0:
            return ExecuteResponse(stdout="", stderr=compile_result.stderr)
        try:
            run_result = subprocess.run(
                [java, "-jar", jar],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=run_result.stdout, stderr=run_result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

_SLOW_LANGS = {"groovy"}  # JVM startup needs more time

def _run_scala(code: str) -> ExecuteResponse:
    scalac = _find_binary(["scalac"]) or "scalac"
    java = _find_binary(["java"]) or "java"
    scala_lib = _find_scala_lib()

    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "Main.scala")
        with open(src, "w") as f:
            f.write(code)
        compile_result = subprocess.run(
            [scalac, src, "-d", tmpdir],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if compile_result.returncode != 0:
            # Filter deprecation warnings from stderr
            err = "\n".join(
                l for l in compile_result.stderr.splitlines() if "warning" not in l.lower()
            )
            return ExecuteResponse(stdout="", stderr=err or compile_result.stderr)
        m = re.search(r"object\s+(\w+)", code)
        obj_name = m.group(1) if m else "Main"
        cp = f"{tmpdir}:{scala_lib}" if scala_lib else tmpdir
        try:
            run_result = subprocess.run(
                [java, "-cp", cp, obj_name],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_JVM,
            )
            return ExecuteResponse(stdout=run_result.stdout, stderr=run_result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(stdout="", stderr=f"Execution timed out after {TIMEOUT_JVM}s.")

def _run_simple(lang: str, code: str) -> ExecuteResponse:
    binary_name, ext = _SIMPLE_RUNNERS[lang]
    binary = _find_binary([binary_name])
    if not binary:
        raise HTTPException(
            status_code=500, detail=f"Runtime '{binary_name}' not found on this server."
        )
    timeout = TIMEOUT_JVM if lang in _SLOW_LANGS else TIMEOUT_SECONDS
    with tempfile.TemporaryDirectory() as tmpdir:
        code_file = os.path.join(tmpdir, f"main{ext}")
        with open(code_file, "w") as f:
            f.write(code)
        try:
            result = subprocess.run(
                [binary, code_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )
        except FileNotFoundError:
            raise HTTPException(
                status_code=500, detail=f"Runtime '{binary_name}' is not installed."
            )

def _run_compiled_single(
    lang: str,
    code: str,
    binary_name: str,
    ext: str,
    compile_cmd_fn,
    run_cmd_fn,
    timeout: int = TIMEOUT_SECONDS,
) -> ExecuteResponse:
    """Generic compile-then-run for single-file compiled languages."""
    binary = _find_binary([binary_name])
    if not binary:
        raise HTTPException(status_code=500, detail=f"Runtime '{binary_name}' not installed.")
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, f"main{ext}")
        out = os.path.join(tmpdir, "main")
        with open(src, "w") as f:
            f.write(code)
        compile_result = subprocess.run(
            compile_cmd_fn(binary, src, out),
            capture_output=True,
            text=True,
            timeout=60,
            cwd=tmpdir,  # some compilers (e.g. valac) emit intermediates in CWD
        )
        if compile_result.returncode != 0:
            return ExecuteResponse(stdout="", stderr=compile_result.stderr)
        try:
            run_result = subprocess.run(
                run_cmd_fn(out),
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=run_result.stdout, stderr=run_result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(stdout="", stderr=f"Execution timed out after {timeout}s.")

def _run_crystal(code: str) -> ExecuteResponse:
    return _run_compiled_single(
        "crystal", code, "crystal", ".cr", lambda b, s, o: [b, "build", s, "-o", o], lambda o: [o]
    )

def _run_nim(code: str) -> ExecuteResponse:
    return _run_compiled_single(
        "nim",
        code,
        "nim",
        ".nim",
        lambda b, s, o: [b, "compile", "--verbosity:0", "--hints:off", f"--out:{o}", s],
        lambda o: [o],
    )

def _run_d(code: str) -> ExecuteResponse:
    return _run_compiled_single(
        "d", code, "gdc", ".d", lambda b, s, o: [b, s, "-o", o], lambda o: [o]
    )

def _run_vala(code: str) -> ExecuteResponse:
    return _run_compiled_single(
        "vala", code, "valac", ".vala", lambda b, s, o: [b, s, "-o", o], lambda o: [o]
    )

def _run_pascal(code: str) -> ExecuteResponse:
    # fpc writes the binary to the path given by -o<file> (no space after -o)
    return _run_compiled_single(
        "pascal", code, "fpc", ".pas", lambda b, s, o: [b, f"-o{o}", s], lambda o: [o]
    )

def _run_ada(code: str) -> ExecuteResponse:
    # GNAT requires the source file to be named after its main procedure unit.
    gnatmake = _find_binary(["gnatmake"])
    if not gnatmake:
        raise HTTPException(status_code=500, detail="Runtime 'gnatmake' not installed.")
    m = re.search(r"procedure\s+(\w+)", code)
    unit = (m.group(1) if m else "Main").lower()
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, f"{unit}.adb")
        with open(src, "w") as f:
            f.write(code)
        compile_result = subprocess.run(
            [gnatmake, "-q", src],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=tmpdir,
        )
        if compile_result.returncode != 0:
            return ExecuteResponse(stdout="", stderr=compile_result.stderr or compile_result.stdout)
        try:
            run_result = subprocess.run(
                [os.path.join(tmpdir, unit)],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=run_result.stdout, stderr=run_result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_scripted(
    code: str,
    binary_candidates: list,
    ext: str,
    build_args,
    timeout: int = TIMEOUT_SECONDS,
) -> ExecuteResponse:
    """Run an interpreter that needs extra argv flags (not just [binary, file])."""
    binary = _find_binary(binary_candidates)
    if not binary:
        raise HTTPException(
            status_code=500, detail=f"Runtime '{binary_candidates[0]}' not installed."
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, f"main{ext}")
        with open(src, "w") as f:
            f.write(code)
        try:
            result = subprocess.run(
                build_args(binary, src),
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(stdout="", stderr=f"Execution timed out after {timeout}s.")

def _run_forth(code: str) -> ExecuteResponse:
    # gforth loads the file then needs an explicit `bye` to exit (else it hangs in the REPL)
    return _run_scripted(code, ["gforth"], ".fth", lambda b, s: [b, s, "-e", "bye"])

def _run_chicken(code: str) -> ExecuteResponse:
    return _run_scripted(code, ["chicken-csi", "csi"], ".scm", lambda b, s: [b, "-s", s])

def _run_v(code: str) -> ExecuteResponse:
    return _run_scripted(code, ["v"], ".v", lambda b, s: [b, "run", s], timeout=TIMEOUT_JVM)

def _run_objc(code: str) -> ExecuteResponse:
    return _run_compiled_single(
        "objc", code, "gcc", ".m", lambda b, s, o: [b, s, "-o", o, "-lobjc"], lambda o: [o]
    )

def _run_zig(code: str) -> ExecuteResponse:
    # Zig auto-wraps if no pub fn main
    if "pub fn main" not in code:
        fns = re.findall(r"(?:pub\s+)?fn\s+(\w+)", code)
        calls = "\n    ".join(f"{fn}();" for fn in fns if fn != "main")
        code = code.rstrip() + f"\n\npub fn main() void {{\n    {calls}\n}}\n"
    zig = _find_binary(["zig"]) or "zig"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.zig")
        out = os.path.join(tmpdir, "main")
        with open(src, "w") as f:
            f.write(code)
        compile_result = subprocess.run(
            [zig, "build-exe", src, f"-femit-bin={out}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if compile_result.returncode != 0:
            return ExecuteResponse(stdout="", stderr=compile_result.stderr)
        try:
            run_result = subprocess.run(
                [out],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
            )
            # Zig's debug.print goes to stderr — merge into stdout for display
            combined_stdout = run_result.stdout + run_result.stderr
            return ExecuteResponse(stdout=combined_stdout, stderr="")
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_csharp(code: str, lang: str = "csharp") -> ExecuteResponse:
    dotnet = _find_binary(["dotnet"]) or "dotnet"
    ext = ".fs" if lang in ("fsharp", "fs", "f#") else ".cs"
    proj_type = "console" if lang not in ("fsharp", "fs", "f#") else "console"
    lang_flag = "F#" if lang in ("fsharp", "fs", "f#") else "C#"
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal dotnet console project
        subprocess.run(
            [dotnet, "new", "console", f"--language={lang_flag}", "--no-restore", "-o", tmpdir],
            capture_output=True,
            timeout=30,
        )
        # Overwrite the generated Program file
        prog = os.path.join(tmpdir, f"Program{ext}")
        with open(prog, "w") as f:
            f.write(code)
        restore = subprocess.run(
            [dotnet, "restore", "--nologo"], capture_output=True, text=True, timeout=60, cwd=tmpdir
        )
        build = subprocess.run(
            [dotnet, "run", "--no-build" if False else "--nologo"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_JVM,
            cwd=tmpdir,
        )
        return ExecuteResponse(stdout=build.stdout, stderr=build.stderr)

def _run_prolog(code: str) -> ExecuteResponse:
    swipl = _find_binary(["swipl"]) or "swipl"
    # Auto-add initialization if missing
    if "initialization" not in code and ":- main" not in code:
        code = code.rstrip() + "\n:- initialization(main, main).\nmain :- halt.\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.pl")
        with open(src, "w") as f:
            f.write(code)
        try:
            result = subprocess.run(
                [swipl, "-q", "-f", src],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
            return ExecuteResponse(stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_cobol(code: str) -> ExecuteResponse:
    return _run_compiled_single(
        "cobol", code, "cobc", ".cob", lambda b, s, o: [b, "-x", s, "-o", o], lambda o: [o]
    )

def _run_fortran(code: str) -> ExecuteResponse:
    return _run_compiled_single(
        "fortran", code, "gfortran", ".f90", lambda b, s, o: [b, s, "-o", o], lambda o: [o]
    )

def _run_awk(code: str) -> ExecuteResponse:
    awk = _find_binary(["awk", "gawk"]) or "awk"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.awk")
        with open(src, "w") as f:
            f.write(code)
        try:
            result = subprocess.run(
                [awk, "-f", src],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
            return ExecuteResponse(stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_sml(code: str) -> ExecuteResponse:
    sml = _find_binary(["sml", "poly"]) or "sml"
    # polyml's binary is `poly` and runs scripts via `poly --script`;
    # SML/NJ's `sml` takes the file directly.
    is_poly = os.path.basename(sml) == "poly"
    cmd = [sml, "--script", "{src}"] if is_poly else [sml, "{src}"]
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.sml")
        with open(src, "w") as f:
            f.write(code)
        try:
            result = subprocess.run(
                [a.format(src=src) for a in cmd],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
            # Strip SML banner and REPL noise from stdout
            out = "\n".join(
                l
                for l in result.stdout.splitlines()
                if not l.startswith("Standard ML")
                and not l.startswith("[opening")
                and not l.startswith("val it =")
                and l.strip() != "-"
            )
            return ExecuteResponse(stdout=out.strip(), stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_haxe(code: str) -> ExecuteResponse:
    haxe = _find_binary(["haxe"]) or "haxe"
    # Locate the Haxe std library across platforms (homebrew on macOS, apt on Linux).
    # If none is found, leave HAXE_STD_PATH unset so haxe uses its compiled-in default.
    env = {**os.environ}
    for std in (
        "/opt/homebrew/lib/haxe/std",
        "/usr/local/lib/haxe/std",
        "/usr/share/haxe/std",
        "/usr/lib/haxe/std",
    ):
        if os.path.isdir(std):
            env["HAXE_STD_PATH"] = std
            break
    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract class name
        m = re.search(r"class\s+(\w+)", code)
        class_name = m.group(1) if m else "Main"
        src = os.path.join(tmpdir, f"{class_name}.hx")
        with open(src, "w") as f:
            f.write(code)
        try:
            result = subprocess.run(
                [haxe, "--main", class_name, "--interp"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
                env=env,
            )
            return ExecuteResponse(stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_odin(code: str) -> ExecuteResponse:
    odin = _find_binary(["odin"]) or "odin"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.odin")
        with open(src, "w") as f:
            f.write(code)
        try:
            result = subprocess.run(
                [odin, "run", src, "-file"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_sbcl(code: str) -> ExecuteResponse:
    sbcl = _find_binary(["sbcl"]) or "sbcl"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.lisp")
        with open(src, "w") as f:
            f.write(code)
        try:
            result = subprocess.run(
                [sbcl, "--script", src],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
            return ExecuteResponse(stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_octave(code: str) -> ExecuteResponse:
    octave = _find_binary(["octave-cli", "octave"]) or "octave-cli"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.m")
        with open(src, "w") as f:
            f.write(code)
        try:
            result = subprocess.run(
                [octave, "--no-gui", "--norc", src],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
            return ExecuteResponse(stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

def _run_clojure(code: str) -> ExecuteResponse:
    clojure = _find_binary(["clojure"]) or "clojure"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.clj")
        with open(src, "w") as f:
            f.write(code)
        try:
            result = subprocess.run(
                [clojure, "-e", f'(load-file "{src}")'],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_JVM,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(stdout="", stderr=f"Execution timed out after {TIMEOUT_JVM}s.")

def _run_nasm(code: str) -> ExecuteResponse:
    import platform

    nasm = _find_binary(["nasm"])
    if not nasm:
        raise HTTPException(status_code=500, detail="NASM assembler not installed.")
    if platform.machine() not in ("x86_64", "AMD64"):
        return ExecuteResponse(
            stdout="",
            stderr=(
                "x86-64 NASM assembly can only run on an x86-64 host; "
                f"this server is {platform.machine()}."
            ),
        )
    is_linux = platform.system() == "Linux"
    fmt = "elf64" if is_linux else "macho64"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.asm")
        obj = os.path.join(tmpdir, "main.o")
        binary = os.path.join(tmpdir, "main")
        with open(src, "w") as f:
            f.write(code)
        compile_result = subprocess.run(
            [nasm, f"-f{fmt}", src, "-o", obj],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if compile_result.returncode != 0:
            return ExecuteResponse(stdout="", stderr=compile_result.stderr)
        if is_linux:
            link_cmd = ["ld", obj, "-o", binary]
        else:
            link_cmd = ["ld", "-macosx_version_min", "10.13", "-lSystem", obj, "-o", binary]
        link_result = subprocess.run(link_cmd, capture_output=True, text=True, timeout=30)
        if link_result.returncode != 0:
            return ExecuteResponse(stdout="", stderr=link_result.stderr)
        try:
            run_result = subprocess.run(
                [binary],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
            )
            return ExecuteResponse(stdout=run_result.stdout, stderr=run_result.stderr)
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                stdout="", stderr=f"Execution timed out after {TIMEOUT_SECONDS}s."
            )

# ── Public entry point ────────────────────────────────────────────────────────

def run_code(payload: ExecuteRequest, current_user: User) -> ExecuteResponse:
    lang = payload.language.lower().strip()

    # Apply auto-wrapping before execution (same for both Docker and subprocess)
    code = _apply_autowrap(lang, payload.code)

    # SQL always runs via built-in sqlite3 (no Docker needed)
    if lang in _SQL_LANGS:
        return _run_sql(code)

    # Validate before dispatch so Docker and subprocess modes enforce the same 400 path.
    if lang not in _AVAILABLE_RUNTIMES:
        raise HTTPException(
            status_code=400,
            detail=f"Language '{payload.language}' is not available on this server.",
        )

    # Docker path
    if USE_DOCKER:
        return _run_in_docker(lang, code)

    # Subprocess dispatch
    if lang in _JS_LANGS:
        return _run_javascript(code, lang)
    if lang in _JAVA_LANGS:
        return _run_java(code)
    if lang in _CPP_LANGS:
        return _run_cpp(code, lang)
    if lang in _C_LANGS:
        return _run_cpp(code, "c")
    if lang in ("rust", "rs"):
        return _run_rust(code)
    if lang in ("go", "golang"):
        return _run_go(code)
    if lang in ("kotlin", "kt"):
        return _run_kotlin(code)
    if lang in ("scala",):
        return _run_scala(code)
    if lang in ("crystal", "cr"):
        return _run_crystal(code)
    if lang in ("nim",):
        return _run_nim(code)
    if lang in ("zig",):
        return _run_zig(code)
    if lang in ("csharp", "cs", "c#", "fsharp", "fs", "f#"):
        return _run_csharp(code, lang)
    if lang in ("prolog", "pl2"):
        return _run_prolog(code)
    if lang in ("cobol", "cob", "cbl"):
        return _run_cobol(code)
    if lang in ("fortran", "f90", "f95", "f77"):
        return _run_fortran(code)
    if lang in ("awk",):
        return _run_awk(code)
    if lang in ("sml", "standardml"):
        return _run_sml(code)
    if lang in ("haxe", "hx"):
        return _run_haxe(code)
    if lang in ("odin",):
        return _run_odin(code)
    if lang in ("commonlisp", "common-lisp", "cl", "lisp2"):
        return _run_sbcl(code)
    if lang in ("octave", "matlab"):
        return _run_octave(code)
    if lang in ("clojure", "clj"):
        return _run_clojure(code)
    if lang in ("nasm", "asm", "assembly"):
        return _run_nasm(code)
    if lang in ("d", "dlang"):
        return _run_d(code)
    if lang in ("vala",):
        return _run_vala(code)
    if lang in ("pascal", "pas"):
        return _run_pascal(code)
    if lang in ("ada", "adb"):
        return _run_ada(code)
    if lang in ("forth", "fth"):
        return _run_forth(code)
    if lang in ("chicken", "chickenscheme"):
        return _run_chicken(code)
    if lang in ("objc", "objective-c", "objectivec"):
        return _run_objc(code)
    if lang in ("v", "vlang"):
        return _run_v(code)
    if lang in _SIMPLE_RUNNERS:
        return _run_simple(lang, code)

    raise HTTPException(status_code=400, detail=f"Language '{payload.language}' is not supported.")
