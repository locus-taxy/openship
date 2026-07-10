#!/usr/bin/env python3
"""Smoke-test every sandbox language by actually executing a hello-world snippet.

Runs each snippet through the real run_code dispatch (subprocess mode) and reports
PASS/FAIL/SKIP. SKIP = runtime not installed on this host. Used to verify which
languages are genuinely operable on a given environment (local dev box or Docker image).

Usage: python3 scripts/smoke_test_languages.py
"""

import os
import sys

os.environ.setdefault("SANDBOX_USE_DOCKER", "false")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import controllers.execute as ec  # noqa: E402
from schemas.execute import ExecuteRequest  # noqa: E402

# One representative snippet per language. Expected substring in stdout = "ok".
CASES = [
    ("python", "print('ok')"),
    ("javascript", "console.log('ok')"),
    ("typescript", "const x: string = 'ok'; console.log(x)"),
    ("ruby", "puts 'ok'"),
    ("bash", "echo ok"),
    ("go", 'package main\nimport "fmt"\nfunc main(){fmt.Println("ok")}'),
    ("rust", 'fn main(){println!("ok");}'),
    ("java", 'public class Main{public static void main(String[] a){System.out.println("ok");}}'),
    ("cpp", '#include <iostream>\nint main(){std::cout<<"ok"<<std::endl;}'),
    ("c", '#include <stdio.h>\nint main(){printf("ok\\n");}'),
    ("php", "<?php echo 'ok';"),
    ("perl", "print 'ok'"),
    ("lua", "print('ok')"),
    ("kotlin", 'fun main(){println("ok")}'),
    ("dart", "void main(){print('ok');}"),
    ("scala", 'object Main extends App { println("ok") }'),
    ("elixir", 'IO.puts "ok"'),
    ("julia", 'println("ok")'),
    ("r", 'cat("ok\\n")'),
    ("groovy", "println 'ok'"),
    ("powershell", "Write-Output 'ok'"),
    ("haskell", 'main = putStrLn "ok"'),
    ("csharp", 'using System; class P{static void Main(){Console.WriteLine("ok");}}'),
    ("fsharp", 'printfn "ok"'),
    ("crystal", 'puts "ok"'),
    ("ocaml", 'print_string "ok"'),
    ("racket", '#lang racket\n(display "ok")'),
    ("nim", 'echo "ok"'),
    ("zig", 'const std=@import("std");pub fn main() void {std.debug.print("ok\\n",.{});}'),
    ("deno", "console.log('ok')"),
    ("erlang", '-module(main).\n-export([main/1]).\nmain(_) -> io:format("ok~n").'),
    ("octave", 'disp("ok")'),
    ("prolog", ":- initialization(main).\nmain :- write('ok'), nl."),
    ("odin", 'package main\nimport "core:fmt"\nmain :: proc(){fmt.println("ok")}'),
    (
        "cobol",
        '       IDENTIFICATION DIVISION.\n       PROGRAM-ID. H.\n       PROCEDURE DIVISION.\n           DISPLAY "ok".\n           STOP RUN.',
    ),
    ("commonlisp", '(format t "ok")'),
    ("sml", 'print "ok";'),
    ("tcl", 'puts "ok"'),
    ("awk", 'BEGIN { print "ok" }'),
    ("fortran", 'program p\n  print *, "ok"\nend program'),
    ("haxe", 'class Main { static function main() { trace("ok"); } }'),
    ("clojure", '(println "ok")'),
    ("coffeescript", "console.log 'ok'"),
    (
        "nasm",
        'section .data\nmsg db "ok",10\nsection .text\nglobal _start\n_start:\nmov rax,1\nmov rdi,1\nmov rsi,msg\nmov rdx,3\nsyscall\nmov rax,60\nxor rdi,rdi\nsyscall',
    ),
    ("sql", "SELECT 'ok' AS col;"),
    ("swift", 'print("ok")'),
    # ── batch 1 ──
    ("fish", "echo ok"),
    ("raku", 'say "ok"'),
    ("guile", '(display "ok")(newline)'),
    ("d", 'import std.stdio; void main(){writeln("ok");}'),
    ("vala", 'void main(){print("ok\\n");}'),
    ("pascal", "begin writeln('ok'); end."),
    ("ada", 'with Ada.Text_IO; procedure Main is begin Ada.Text_IO.Put_Line("ok"); end Main;'),
    # ── batch 2 ──
    ("zsh", "echo ok"),
    ("ksh", "echo ok"),
    ("tcsh", "echo ok"),
    ("luajit", "print('ok')"),
    ("clisp", '(format t "ok")'),
    ("newlisp", '(println "ok")'),
    ("rexx", "say 'ok'"),
    ("expect", 'send_user "ok\\n"'),
    ("m4", "ok"),
    ("gambit", '(display "ok")(newline)'),
    ("pike", 'int main(){write("ok\\n");}'),
    ("yabasic", 'print "ok"'),
    ("algol68", 'print(("ok", new line))'),
    ("forth", '." ok" cr'),
    ("chicken", '(print "ok")'),
    ("objc", '#include <stdio.h>\nint main(){printf("ok\\n");return 0;}'),
    ("v", "fn main(){println('ok')}"),
]

def main():
    avail = ec._detect_runtimes()
    results = {"PASS": [], "FAIL": [], "SKIP": []}
    details = []
    for lang, code in CASES:
        if lang not in avail:
            results["SKIP"].append(lang)
            details.append((lang, "SKIP", "runtime not installed"))
            continue
        try:
            resp = ec.run_code(ExecuteRequest(language=lang, code=code), None)
            out = (resp.stdout or "") + (resp.stderr or "")
            if "ok" in resp.stdout.lower():
                results["PASS"].append(lang)
                details.append((lang, "PASS", resp.stdout.strip()[:60]))
            else:
                results["FAIL"].append(lang)
                details.append((lang, "FAIL", (out.strip()[:120] or "no output")))
        except Exception as e:
            results["FAIL"].append(lang)
            details.append((lang, "FAIL", f"{type(e).__name__}: {str(e)[:100]}"))

    print(f"{'LANG':<16} {'STATUS':<6} DETAIL")
    print("-" * 80)
    for lang, status, detail in details:
        print(f"{lang:<16} {status:<6} {detail}")
    print("-" * 80)
    print(
        f"TOTAL {len(CASES)}  |  PASS {len(results['PASS'])}  "
        f"FAIL {len(results['FAIL'])}  SKIP {len(results['SKIP'])}"
    )
    if results["FAIL"]:
        print("FAILED:", ", ".join(results["FAIL"]))
    if results["SKIP"]:
        print("SKIPPED (no runtime):", ", ".join(results["SKIP"]))
    if results["FAIL"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
