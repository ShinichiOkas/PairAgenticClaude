"""文字の類似（機械）: 文字 2-gram（かな・漢字）と英単語の TF-IDF の余弦。LLM に回す組を絞るふるい。"""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
from scipy import sparse

from .survey import split_frontmatter

_WORD = re.compile(r"[a-z][a-z0-9_\-]{1,}")
_CJK = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ]+")
_NOISE = re.compile(r"^(created_at|updated_at|confirmed_at|maturity|proposed_by|approved_by|confirmed_by|source\w*|domain_tags|category|type|skill_id|status)\s*:.*$", re.M)


def features(text: str) -> Counter[str]:
    fm, body = split_frontmatter(text)
    head = " ".join(str(fm.get(k, "")) for k in ("name", "description"))
    t = _NOISE.sub("", head + "\n" + body).lower()
    c: Counter[str] = Counter(_WORD.findall(t))
    for run in _CJK.findall(t):
        if len(run) == 1:
            c[run] += 1
        for i in range(len(run) - 1):
            c[run[i:i + 2]] += 1
    return c


def similarity_matrix(texts: list[str]) -> sparse.csr_matrix:
    """行ごとに L2 正規化した TF-IDF の積（余弦）。対角は 0。"""
    feats = [features(t) for t in texts]
    n = len(feats)
    df: Counter[str] = Counter()
    for f in feats:
        df.update(f.keys())
    vocab = {w: i for i, w in enumerate(df)}
    idf = {w: math.log((1 + n) / (1 + d)) + 1.0 for w, d in df.items()}
    rows, cols, vals = [], [], []
    for r, f in enumerate(feats):
        ws = [(vocab[w], (1.0 + math.log(c)) * idf[w]) for w, c in f.items()]
        norm = math.sqrt(sum(v * v for _, v in ws)) or 1.0
        for ci, v in ws:
            rows.append(r)
            cols.append(ci)
            vals.append(v / norm)
    x = sparse.csr_matrix((np.array(vals, dtype=np.float32), (rows, cols)), shape=(n, max(1, len(vocab))))
    s = (x @ x.T).tocsr()
    s.setdiag(0)
    s.eliminate_zeros()
    return s


def top_pairs(s: sparse.csr_matrix, k: int, lo: float, hi: float = 1.01) -> list[tuple[int, int, float]]:
    """各行の上位 k 件のうち lo 以上 hi 未満の組（i<j に正規化・重複除去）。"""
    out: dict[tuple[int, int], float] = {}
    for i in range(s.shape[0]):
        start, end = s.indptr[i], s.indptr[i + 1]
        idx, val = s.indices[start:end], s.data[start:end]
        if len(val) == 0:
            continue
        order = np.argsort(-val)[:k]
        for j, v in zip(idx[order], val[order]):
            if lo <= v < hi:
                key = (min(i, int(j)), max(i, int(j)))
                out[key] = round(float(v), 3)
    return sorted(((a, b, v) for (a, b), v in out.items()), key=lambda x: -x[2])
