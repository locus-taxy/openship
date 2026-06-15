#!/bin/bash
# Entrypoint for openship-sandbox container.
# Usage: /run.sh <language> <code_file>
# The code file lives at /sandbox/<filename> (mounted from host).

set -e

LANG="$1"
FILE="$2"
TMPDIR="/sandbox"

# ── JS/TS/React pipeline ──────────────────────────────────────────────────────
run_javascript() {
    local file="$1"
    local out="$TMPDIR/out.js"
    local final="$TMPDIR/run.js"
    local jsdom_path="$JS_SANDBOX_DIR/node_modules/jsdom"

    # Bundle with esbuild (handles JSX + React imports)
    "$JS_SANDBOX_DIR/node_modules/.bin/esbuild" "$file" \
        --bundle --platform=node --format=cjs "--outfile=$out" \
        --log-level=error 2>/tmp/esbuild_err.txt

    if [ $? -ne 0 ]; then
        cat /tmp/esbuild_err.txt >&2
        exit 1
    fi

    # Write runner with jsdom preamble
    cat > "$final" << JSEOF
const { JSDOM } = require('$jsdom_path');
const _dom = new JSDOM('<!DOCTYPE html><html><body><div id="root"></div></body></html>');
const _globals = {
  window: _dom.window, document: _dom.window.document,
  navigator: _dom.window.navigator, location: _dom.window.location,
  HTMLElement: _dom.window.HTMLElement, Element: _dom.window.Element,
  Node: _dom.window.Node, Text: _dom.window.Text,
  Event: _dom.window.Event, CustomEvent: _dom.window.CustomEvent,
  requestAnimationFrame: (cb) => setTimeout(cb, 0),
  cancelAnimationFrame: clearTimeout,
};
for (const [k, v] of Object.entries(_globals)) {
  Object.defineProperty(global, k, { value: v, writable: true, configurable: true });
}
require('$out');
(async () => {
  await new Promise(r => setTimeout(r, 50));
  const root = document.getElementById('root');
  if (root && root.innerHTML.trim()) {
    console.log('\n=== React Output ===');
    console.log(root.innerHTML);
  }
})();
JSEOF

    node "$final"
}

# ── Compiled language helpers ──────────────────────────────────────────────────
compile_and_run() {
    local compile_cmd=("$@")
    "${compile_cmd[@]}" && "$TMPDIR/main"
}

case "$LANG" in
    # ── Scripting ──────────────────────────────────────────────────────────────
    python|python3)       python3 "$FILE" ;;
    ruby|rb)              ruby "$FILE" ;;
    bash|sh|shell)        bash "$FILE" ;;
    perl|pl)              perl "$FILE" ;;
    lua)                  lua5.4 "$FILE" ;;
    php)                  php "$FILE" ;;
    elixir|ex|exs)        elixir "$FILE" ;;
    erlang|erl)           escript "$FILE" ;;
    julia|jl)             julia "$FILE" ;;
    r|rscript)            Rscript "$FILE" ;;
    haskell|hs)           runghc "$FILE" ;;
    ocaml|ml)             ocaml "$FILE" ;;
    racket|rkt|scheme|lisp) racket "$FILE" ;;
    tcl)                  tclsh "$FILE" ;;
    awk)                  awk -f "$FILE" ;;
    groovy)               groovy "$FILE" ;;
    powershell|pwsh|ps1)  pwsh "$FILE" ;;
    commonlisp|cl|lisp2)  sbcl --script "$FILE" ;;
    sml|standardml)       sml "$FILE" ;;
    prolog|pl2)           swipl -q -f "$FILE" ;;
    octave|matlab)        octave --no-gui --norc "$FILE" ;;
    deno)                 deno run "$FILE" ;;
    dart|flutter)         dart run "$FILE" ;;

    # ── JS/TS/React ────────────────────────────────────────────────────────────
    javascript|js|jsx|tsx|typescript|ts|react|vue|node|nodejs|next|nextjs|angular|express)
        run_javascript "$FILE" ;;

    # ── Compiled ───────────────────────────────────────────────────────────────
    java)
        classname=$(grep -oP 'public\s+class\s+\K\w+' "$FILE" | head -1)
        classname="${classname:-Main}"
        javac -d "$TMPDIR" "$FILE" && java -cp "$TMPDIR" "$classname" ;;

    cpp|c++|cxx|cc)
        g++ -std=c++17 "$FILE" -o "$TMPDIR/main" && "$TMPDIR/main" ;;

    c)
        gcc -std=c11 "$FILE" -o "$TMPDIR/main" && "$TMPDIR/main" ;;

    go|golang)
        go run "$FILE" ;;

    rust|rs)
        rustc "$FILE" -o "$TMPDIR/main" && "$TMPDIR/main" ;;

    swift)
        swift "$FILE" ;;

    kotlin|kt)
        kotlinc "$FILE" -include-runtime -d "$TMPDIR/main.jar" 2>/dev/null \
            && java -jar "$TMPDIR/main.jar" ;;

    scala)
        scalac "$FILE" -d "$TMPDIR" 2>/dev/null \
            && objname=$(grep -oP 'object\s+\K\w+' "$FILE" | head -1) \
            && java -cp "$TMPDIR:/opt/scala/lib/*" "${objname:-Main}" ;;

    crystal|cr)
        crystal build "$FILE" -o "$TMPDIR/main" && "$TMPDIR/main" ;;

    nim)
        nim compile --verbosity:0 --hints:off --out:"$TMPDIR/main" "$FILE" && "$TMPDIR/main" ;;

    zig)
        zig build-exe "$FILE" "-femit-bin=$TMPDIR/main" && "$TMPDIR/main" ;;

    csharp|cs|c#|fsharp|fs|f#)
        lang_flag="C#"
        [[ "$LANG" == "fsharp" || "$LANG" == "fs" || "$LANG" == "f#" ]] && lang_flag="F#"
        proj="$TMPDIR/proj"
        mkdir -p "$proj"
        dotnet new console --language="$lang_flag" --no-restore -o "$proj" -f net8.0 >/dev/null 2>&1
        ext=".cs"; [[ "$lang_flag" == "F#" ]] && ext=".fs"
        cp "$FILE" "$proj/Program$ext"
        dotnet run --project "$proj" --nologo 2>/dev/null ;;

    fortran|f90|f95|f77)
        gfortran "$FILE" -o "$TMPDIR/main" && "$TMPDIR/main" ;;

    cobol|cob|cbl)
        cobc -x -free "$FILE" -o "$TMPDIR/main" && "$TMPDIR/main" ;;

    odin)
        odin run "$FILE" -file ;;

    haxe|hx)
        classname=$(grep -oP 'class\s+\K\w+' "$FILE" | head -1)
        classname="${classname:-Main}"
        dest="$TMPDIR/${classname}.hx"
        [ "$FILE" != "$dest" ] && cp "$FILE" "$dest"
        cd "$TMPDIR" && haxe --main "$classname" --interp ;;

    *)
        echo "Language '$LANG' is not supported in this sandbox." >&2
        exit 1 ;;
esac
