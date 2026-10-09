"""Bounded math delimiters and source-faithful course formula substitutions."""
import json
import re
from pathlib import Path

FORMULAS = json.loads((Path(__file__).parent / 'data/formulas.json').read_text(encoding='utf-8'))
KNOWN = sorted({f['source']: f for f in FORMULAS}.values(), key=lambda f: -len(f['source']))
DELIMITERS = ((r'\[', r'\]', True), (r'\(', r'\)', False), ('$$', '$$', True), ('$', '$', False))

def escaped(text, pos):
    count = 0
    while pos > 0 and text[pos-1] == '\\':
        count += 1
        pos -= 1
    return count % 2 == 1

def segments(text, known=True):
    """Retain ordinary text and unmatched delimiters verbatim; never parse HTML."""
    output = []
    def plain(value):
        if not value: return
        if known:
            cursor = 0
            while cursor < len(value):
                matches = [(value.find(f['source'], cursor), f) for f in KNOWN]
                matches = [m for m in matches if m[0] >= 0]
                if not matches: break
                pos, formula = min(matches, key=lambda m: m[0])
                if pos > cursor: output.append({'kind':'text', 'text':value[cursor:pos]})
                output.append({'kind':'math', 'tex':formula['tex'], 'display':formula['display'], 'source':formula['source']})
                cursor = pos + len(formula['source'])
            value = value[cursor:]
        if value: output.append({'kind':'text', 'text':value})
    cursor = start = 0
    while cursor < len(text):
        matched = False
        for opening, closing, display in DELIMITERS:
            if not text.startswith(opening, cursor) or escaped(text, cursor): continue
            if opening == '$' and (text.startswith('$$', cursor) or (cursor and text[cursor-1] == '$')): continue
            end = text.find(closing, cursor + len(opening))
            while end >= 0 and (escaped(text, end) or (opening == '$' and (text.startswith('$$',end) or text[end-1] == '$'))):
                end = text.find(closing, end + len(closing))
            if end < 0: continue
            tex = text[cursor+len(opening):end].strip()
            # Avoid mistaking paired prices for an inline math expression.
            if not tex or (opening == '$' and ('\n' in tex or not re.search(r'[A-Za-z\\=^_{}+*/<>−-]',tex))): continue
            plain(text[start:cursor])
            output.append({'kind':'math', 'tex':tex, 'display':display})
            cursor = end + len(closing)
            start = cursor
            matched = True
            break
        if not matched: cursor += 1
    plain(text[start:])
    return output

ALLOWED = set('alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi rho varrho sigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega frac dfrac sqrt int iint iiint oint sum prod lim sin cos tan arcsin arccos arctan sinh cosh tanh log ln exp min max sup inf left right mathrm mathit mathbf mathsf mathtt mathcal overline underline bar hat widehat tilde widetilde vec dot ddot text times cdot pm mp div approx sim simeq equiv neq leq geq le ge infty partial nabla to rightarrow leftarrow leftrightarrow forall exists in notin subset subseteq cup cap angle perp parallel quad qquad degree'.split())

def validate_tex(tex):
    if not isinstance(tex,str) or not 1 <= len(tex) <= 512: raise ValueError('单条公式限 1–512 字符')
    if re.search(r'[\u2e80-\u9fff\uf900-\ufaff]',tex): raise ValueError('PDF 公式标签请使用英文；中文解释放在公式外的正文中')
    if '$' in tex or any(ord(c)<32 and c not in '\n\t' for c in tex): raise ValueError('公式含无效字符')
    depth = 0
    for pos, char in enumerate(tex):
        if escaped(tex,pos): continue
        if char == '{': depth += 1
        if char == '}': depth -= 1
        if not 0 <= depth <= 16: raise ValueError('公式括号无效或嵌套超过 16 层')
    if depth: raise ValueError('公式括号未闭合')
    for command in re.findall(r'\\([A-Za-z]+|.)',tex):
        if command not in ALLOWED and command not in ',;:! %{}_|':
            raise ValueError('PDF 不支持公式命令 \\' + command + '，请使用常用数学语法')
    return tex
