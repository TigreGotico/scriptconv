# scriptconv documentation

<!-- agent-hint
covers: the reading order of every page in docs/, and the subcommands of the command line
source: the pages in docs/, and scriptconv/__main__.py for the command line
generated: no
verify: python -c '(I:=__import__,re:=I("re"),os:=I("os"),glob:=I("glob"),subprocess:=I("subprocess"),sys:=I("sys"),P:=sorted(os.path.basename(p) for p in glob.glob("docs/*.md") if not p.endswith("index.md")),t:=re.sub(r"<!--.*?--\x3e","",open("docs/index.md",encoding="utf-8").read(),flags=re.S),o:=re.findall(r"^\d+\. \*\*\[([\w-]+\.md)\]",t,re.M),R:=lambda p:re.sub(r"<!--.*?--\x3e|\x60{3}.*?\x60{3}","",open(p,encoding="utf-8").read(),flags=re.S),L:=[(f,u) for f in ["README.md","AGENTS.md"]+["docs/"+p for p in P+["index.md"]] for u in re.findall(r"\]\(([^)#\s]+)",R(f)) if "://" not in u and not os.path.exists(os.path.join(os.path.dirname(f),u))],N:=[(x,y) for x,y in zip(o,o[1:]) if "→\x5d("+y+")" not in R("docs/"+x) or not re.search(r"\[← [^]]*\]\("+re.escape(x)+r"\)",R("docs/"+y))],c:=re.search(r"\{([\w,]+)\}",subprocess.run([sys.executable,"-m","scriptconv","--help"],capture_output=True,text=True).stdout).group(1).split(","),d:=re.findall(r"\x60(\w+)\x60",re.search(r"subcommands: (.*?)\.\n",t,re.S).group(1)),w:=([("pages",P,sorted(o))] if sorted(o)!=P else [])+L+N+([("cli",c,d)] if c!=d else []),print("OK",len(o),"pages",len(c),"subcommands") if not w else sys.exit("BROKEN "+repr(w)))'
see: README.md, AGENTS.md
-->

This index lists every page in reading order. The pages answer, in order of
depth: which writing system a text is in, how to rewrite it in another
representation, how to add or remove its optional marks, and how it sounds.

1. **[stack.md](stack.md)**: where scriptconv sits in the speech stack. A
   walk-through of `TextFrontend` with a normaliser, the order of the stages,
   and the library that runs each stage.
2. **[scripts.md](scripts.md)**: writing-system identity. ISO 15924
   detection (`detect_script`, `char_script`), mixed-script runs
   (`script_runs`), text direction, the language-to-script map and the
   script metadata. The returned tags are stable API.
3. **[notation.md](notation.md)**: phoneme notations through the IPA hub:
   ARPABET with reversible stress, X-SAMPA, Kirshenbaum, Lexique, Cotovía,
   RFE, Buckwalter to Arabic and Halabi. The `errors=` policy and the
   `NOTATION_INFO` fidelity flags.
4. **[translit.md](translit.md)**: table-driven script rewrites: Hangul to
   jamo, hiragana to katakana, and hanzi to Cangjie codes.
5. **[readings.md](readings.md)**: respellings that need a dictionary: kanji
   to kana with the token stream, and hanzi to pinyin or bopomofo.
6. **[conventions.md](conventions.md)**: optional marks as data: tashkeel,
   kashida, Quranic marks, niqqud, teamim, wakachigaki, pinyin tones and jamo
   form, with `strip`, `apply`, `restyle` and `detect_convention`.
7. **[graph.md](graph.md)**: the conversion graph: nodes, edges, routing that
   prefers lossless edges, and explicit extension.
8. **[phonemizers.md](phonemizers.md)**: the phonemizer contract, the
   registry and the per-language defaults, normalisation, identity and the
   sister packages.
9. **[frontend.md](frontend.md)**: every option of `TextFrontend`: inline
   phoneme blocks, chunk sizes, strict mode and its identity.
10. **[ovos.md](ovos.md)**: scriptconv phonemizers in OVOS through
    `ovos-scriptconv-g2p-plugin`.
11. **[backends.md](backends.md)**: every phonemizer backend with its class,
    extra, package and language default, and the models that download on
    first use.

The command line, `python -m scriptconv`, has these subcommands: `convert`,
`detect`, `distribution`, `direction`, `decompose`, `lang`, `strip`,
`restyle`, `conventions`, `route` and `phonemize`.
`python -m scriptconv <subcommand> --help` shows the arguments of each one.
The other functions in these pages have no subcommand.
