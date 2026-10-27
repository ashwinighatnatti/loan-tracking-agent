"""Context pack: the code around the files under review, found by static analysis (ast), not by the model.

For each reviewed file the pack holds, in priority order under a character budget:
  declarations  classes the file uses (field types and defaults: is it Optional? is it "" or None?)
  callees       functions the file calls that live in other files
  callers       places in other files that call what the file defines
  tests         test files exercising the file, plus its public symbols that no test mentions
Resolution is approximate (no type inference), deliberately simple, and never reads the eval answer key."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from .context import is_answer_key
from .rubric import REPO_ROOT

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "eval", ".claude",
             ".github", "build", "dist"}
MAX_CLASS_LINES = 150
MAX_FUNC_LINES = 120
MAX_TEST_CHARS = 6000
MAX_CALLERS = 6
MAX_CALLERS_PER_SYMBOL = 2
DEFAULT_BUDGET = 40_000


@dataclass
class Def:
    name: str
    kind: str  # "class" | "function"
    start: int
    end: int
    bases: list[str] = field(default_factory=list)


@dataclass
class Import:
    kind: str          # "symbol" | "module"
    target: str        # repo-relative path of the module file
    name: str = ""     # symbol name for kind == "symbol"


@dataclass
class FileInfo:
    path: str
    source: str
    tree: ast.AST | None
    defs: dict[str, Def] = field(default_factory=dict)
    imports: dict[str, Import] = field(default_factory=dict)
    error: str = ""


@dataclass
class Item:
    kind: str    # declaration | callee | caller | test | note
    path: str
    start: int
    end: int
    why: str
    text: str    # numbered lines, or free text for notes


@dataclass
class Pack:
    items: list[Item] = field(default_factory=list)
    omitted: int = 0
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        out = []
        for i in self.items:
            span = f' lines="{i.start}-{i.end}"' if i.end else ""
            out.append(f'<context kind="{i.kind}" path="{i.path}"{span} why="{i.why}">\n{i.text}\n</context>')
        return "\n".join(out)

    @property
    def chars(self) -> int:
        return sum(len(i.text) for i in self.items)


# ---- indexing -------------------------------------------------------------------------------------------

def _skip(rel: str) -> bool:
    return any(part in SKIP_DIRS for part in rel.split("/")[:-1]) or is_answer_key(rel)


class Index:
    def __init__(self, root: Path = REPO_ROOT):
        self.root = root
        self.files: dict[str, FileInfo] = {}
        for p in sorted(root.rglob("*.py")):
            rel = p.relative_to(root).as_posix()
            if _skip(rel):
                continue
            self.files[rel] = self._parse(rel, p.read_text(encoding="utf-8", errors="replace"))
        for info in self.files.values():
            if info.tree is not None:
                self._imports(info)

    @staticmethod
    def _parse(rel: str, source: str) -> FileInfo:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return FileInfo(rel, source, None, error=f"does not parse (line {exc.lineno})")
        info = FileInfo(rel, source, tree)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)] if isinstance(node, ast.ClassDef) else []
                info.defs[node.name] = Def(node.name, "class" if isinstance(node, ast.ClassDef) else "function",
                                           start, node.end_lineno or node.lineno, bases)
        return info

    def module_file(self, dotted: str, from_path: str, level: int) -> str | None:
        parts = [p for p in dotted.split(".") if p]
        bases: list[Path]
        if level:
            base = Path(from_path).parent
            for _ in range(level - 1):
                base = base.parent
            bases = [base]
        else:  # absolute, or relative to loan_agent/ because some modules patch sys.path
            bases = [Path("."), Path("loan_agent")]
        for b in bases:
            stem = (b.joinpath(*parts)).as_posix().lstrip("./") if parts else b.as_posix()
            for cand in (f"{stem}.py", f"{stem}/__init__.py"):
                if cand in self.files:
                    return cand
        return None

    def _imports(self, info: FileInfo) -> None:
        for node in ast.walk(info.tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for a in node.names:
                    alias = a.asname or a.name
                    sub = self.module_file(f"{mod}.{a.name}" if mod else a.name, info.path, node.level)
                    if sub:
                        info.imports[alias] = Import("module", sub)
                        continue
                    src = self.module_file(mod, info.path, node.level)
                    if src and a.name in self.files[src].defs:
                        info.imports[alias] = Import("symbol", src, a.name)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    src = self.module_file(a.name, info.path, 0)
                    if src:
                        info.imports[a.asname or a.name.split(".")[0]] = Import("module", src)

    # ---- helpers

    def numbered(self, path: str, start: int, end: int, limit: int) -> tuple[str, int]:
        lines = self.files[path].source.splitlines()
        stop = min(end, start + limit - 1)
        body = "\n".join(f"{i:5d}| {lines[i - 1]}" for i in range(start, stop + 1))
        if stop < end:
            body += f"\n      | ... ({end - stop} more lines)"
        return body, stop


# ---- reference resolution ---------------------------------------------------------------------------------

def _nodes_in(info: FileInfo, spans: list[tuple[int, int]] | None):
    for node in ast.walk(info.tree):
        ln = getattr(node, "lineno", None)
        if spans is None or ln is None or any(a <= ln <= b for a, b in spans):
            yield node


def references(index: Index, info: FileInfo, spans=None) -> list[tuple[str, str]]:
    """(target path, symbol) pairs this file refers to that are defined in other repo files."""
    found: dict[tuple[str, str], None] = {}
    for node in _nodes_in(info, spans):
        if isinstance(node, ast.Name) and node.id in info.imports:
            imp = info.imports[node.id]
            if imp.kind == "symbol":
                found[(imp.target, imp.name)] = None
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            imp = info.imports.get(node.value.id)
            if imp and imp.kind == "module" and node.attr in index.files[imp.target].defs:
                found[(imp.target, node.attr)] = None
    return [k for k in found if k[0] != info.path]


def _callers_of(index: Index, target: FileInfo) -> list[tuple[str, int, str, str]]:
    """(caller path, call line, enclosing def name, symbol) for calls into `target` from non-test code."""
    out = []
    for path, info in index.files.items():
        if info.tree is None or path == target.path or path.startswith("tests/"):
            continue
        for node in ast.walk(info.tree):
            if not isinstance(node, ast.Call):
                continue
            sym = None
            f = node.func
            if isinstance(f, ast.Name):
                imp = info.imports.get(f.id)
                if imp and imp.kind == "symbol" and imp.target == target.path:
                    sym = imp.name
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                imp = info.imports.get(f.value.id)
                if imp and imp.kind == "module" and imp.target == target.path and f.attr in target.defs:
                    sym = f.attr
            if sym:
                encl = next((d.name for d in info.defs.values() if d.start <= node.lineno <= d.end), "<module>")
                out.append((path, node.lineno, encl, sym))
    return out


def _test_refs(index: Index, target: FileInfo) -> dict[str, set[str]]:
    """{test file: symbols of `target` it uses}."""
    hits: dict[str, set[str]] = {}
    for path, info in index.files.items():
        if info.tree is None or not path.startswith("tests/") or path == target.path:
            continue
        used = {name for name, imp in info.imports.items()
                if imp.target == target.path and imp.kind == "symbol"}
        used = {info.imports[n].name for n in used}
        for node in ast.walk(info.tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                imp = info.imports.get(node.value.id)
                if imp and imp.kind == "module" and imp.target == target.path and node.attr in target.defs:
                    used.add(node.attr)
        if used:
            hits[path] = used
    return hits


def _spans_for_changes(info: FileInfo, changed: set[int] | None) -> list[tuple[int, int]] | None:
    if not changed:
        return None
    spans = [(d.start, d.end) for d in info.defs.values() if any(d.start <= ln <= d.end for ln in changed)]
    return spans or None


# ---- the pack -------------------------------------------------------------------------------------------

def build_pack(paths: list[str], root: Path = REPO_ROOT, budget: int = DEFAULT_BUDGET,
               changed: dict[str, set[int]] | None = None, index: Index | None = None) -> Pack:
    index = index or Index(root)
    pack = Pack()
    reviewed = set(paths)
    candidates: list[tuple[int, Item]] = []  # (priority, item); lower first
    seen: set[tuple[str, str]] = set()

    def add_def(prio: int, kind: str, path: str, name: str, why: str) -> None:
        if (path, name) in seen or path in reviewed:
            return
        seen.add((path, name))
        d = index.files[path].defs[name]
        text, stop = index.numbered(path, d.start, d.end, MAX_CLASS_LINES if d.kind == "class" else MAX_FUNC_LINES)
        candidates.append((prio, Item(kind, path, d.start, stop, why, text)))

    for rel in paths:
        info = index.files.get(rel)
        if info is None:
            if rel.endswith(".py"):
                pack.notes.append(f"{rel}: not indexed, no context gathered")
            continue
        if info.tree is None:
            pack.notes.append(f"{rel}: {info.error}, so no context could be gathered for it")
            continue
        spans = _spans_for_changes(info, (changed or {}).get(rel))
        for target, name in references(index, info, spans):
            d = index.files[target].defs[name]
            if d.kind == "class":
                add_def(0, "declaration", target, name, f"type used by {rel}")
                for base in d.bases:  # one level of inheritance (mixins carry defaults too)
                    tgt = index.files[target]
                    if base in tgt.defs:
                        add_def(1, "declaration", target, base, f"base of {name}")
                    elif base in tgt.imports and tgt.imports[base].kind == "symbol":
                        add_def(1, "declaration", tgt.imports[base].target, tgt.imports[base].name, f"base of {name}")
            else:
                add_def(2, "callee", target, name, f"called by {rel}")

        defined = {n for n, d in info.defs.items()
                   if spans is None or any(a <= d.end and d.start <= b for a, b in spans)}
        per_symbol: dict[str, int] = {}
        callers = 0
        for cpath, line, encl, sym in _callers_of(index, info):
            if sym not in defined or callers >= MAX_CALLERS or per_symbol.get(sym, 0) >= MAX_CALLERS_PER_SYMBOL:
                continue
            per_symbol[sym] = per_symbol.get(sym, 0) + 1
            callers += 1
            cinfo = index.files[cpath]
            d = cinfo.defs.get(encl)
            a, b = (d.start, d.end) if d and d.end - d.start < 40 else (max(1, line - 4), line + 4)
            if any(c.kind == "caller" and c.path == cpath and a <= c.end and c.start <= b for _, c in candidates):
                continue  # overlaps a snippet already collected from the same place
            text, stop = index.numbered(cpath, a, b, 40)
            candidates.append((3, Item("caller", cpath, a, stop, f"calls {sym} from {rel}", text)))

        if not rel.startswith("tests/"):
            refs = _test_refs(index, info)
            for tpath in sorted(refs, key=lambda p: -len(refs[p]))[:2]:
                tinfo = index.files[tpath]
                body = tinfo.source if len(tinfo.source) <= MAX_TEST_CHARS else tinfo.source[:MAX_TEST_CHARS] + "\n... (truncated)"
                numbered = "\n".join(f"{i:5d}| {l}" for i, l in enumerate(body.splitlines(), 1))
                candidates.append((4, Item("test", tpath, 1, len(body.splitlines()),
                                           f"tests that use {', '.join(sorted(refs[tpath]))} from {rel}", numbered)))
            used = set().union(*refs.values()) if refs else set()
            untested = sorted(n for n in defined if not n.startswith("_") and n not in used)
            note = (f"Public symbols of {rel} that no test file imports or references: "
                    f"{', '.join(untested) if untested else 'none'}. "
                    f"Test files found for it: {', '.join(sorted(refs)) if refs else 'none'}.")
            candidates.append((4, Item("note", rel, 0, 0, "test coverage by name", note)))

    used_chars = 0
    for _, item in sorted(candidates, key=lambda c: c[0]):  # stable: keeps discovery order within a priority
        if used_chars + len(item.text) > budget and item.kind != "note":
            pack.omitted += 1
            continue
        pack.items.append(item)
        used_chars += len(item.text)
    return pack


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(diff: str) -> dict[str, set[int]]:
    """{file: added/changed line numbers} from a unified diff."""
    out: dict[str, set[int]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:].strip()
            out.setdefault(current, set())
        elif current and (m := _HUNK.match(line)):
            start, count = int(m.group(1)), int(m.group(2) or 1)
            out[current].update(range(start, start + max(count, 1)))
    return out
