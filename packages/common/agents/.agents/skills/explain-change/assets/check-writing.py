#!/usr/bin/env python3
"""Check an explainer page against references/writing-guide.md budgets.
Usage: check-writing.py <page.html> [small|material|index]
Exit 1 on any failure. Counts words in the rendered text, ignoring <style> and <script>."""
import html, re, sys
path = sys.argv[1]
kind = sys.argv[2] if len(sys.argv) > 2 else 'small'
budget = {'small': 1200, 'material': 2500, 'index': 900}[kind]
src = open(path, encoding='utf-8').read()
body = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', src, flags=re.S)
body = re.sub(r'<pre[^>]*>.*?</pre>', ' ', body, flags=re.S)
body = re.sub(r'</(p|li|dd|dt|td|th|h[1-6]|div|figcaption|span|button|title)>', '. ', body)
text = html.unescape(re.sub(r'<[^>]+>', ' ', body))
text = re.sub(r'(\.\s*){2,}', '. ', text)
text = re.sub(r'\s+', ' ', text).strip()
words = text.split()
fails = []
if len(words) > budget:
    fails.append(f'word count {len(words)} exceeds {budget} for a {kind} page')
sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.split()) > 3]
long = [s for s in sents if len(s.split()) > 26]
if long:
    fails.append(f'{len(long)} sentences over 26 words; first: "{long[0][:120]}..."')
avg = sum(len(s.split()) for s in sents) / max(len(sents), 1)
if avg > 20:
    fails.append(f'average sentence length {avg:.1f} exceeds 20')
banned = ['just', 'simply', 'easily', 'basically', 'in order to', 'please', 'leverage', 'utilise', 'utilize',
          'robust', 'seamless', 'actionable', 'currently', 'as of this writing', 'e.g.', 'i.e.', 'etc.']
hits = {w: len(re.findall(r'(?<![\w`])' + re.escape(w) + r'(?![\w`])', text, flags=re.I)) for w in banned}
hits = {w: n for w, n in hits.items() if n}
if hits:
    fails.append('banned words: ' + ', '.join(f'{w} x{n}' for w, n in hits.items()))
if 'Read this first' not in src:
    fails.append('missing "Read this first" block')
if re.search('[\u2013\u2014]', src):
    fails.append('en or em dash present')
if src.count('explain-change page stylesheet') != 1 or src.count('explain-change page script') != 1:
    fails.append('asset markers missing or duplicated')
print(f'{path}: {len(words)} words, {len(sents)} sentences, avg {avg:.1f}, max {max((len(s.split()) for s in sents), default=0)}')
for f in fails:
    print('FAIL', f)
sys.exit(1 if fails else 0)
