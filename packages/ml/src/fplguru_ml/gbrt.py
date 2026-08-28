"""Pure-numpy gradient-boosted regression trees (L2 + pinball/quantile loss).

No LightGBM / scikit-learn: Smart App Control blocks their native binaries, and
the rest of this ML stack is hand-rolled for the same reason (see ``ridge.py``).
Each boosting round fits one shallow regression tree to the current gradient by
greedy variance-reduction splitting; predictions are the base value plus the
learning-rate-scaled sum of tree outputs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

_MAX_BINS = 64  # candidate split thresholds sampled per feature on wide columns


@dataclass
class _Node:
    feat: int = -1  # -1 marks a leaf
    thr: float = 0.0
    left: int = -1
    right: int = -1
    value: float = 0.0  # leaf output (mean gradient of the rows that fall here)


def _fit_tree(x, g, max_depth, min_leaf, rng, colsample):
    """Fit one regression tree to gradient vector ``g``; return a flat list[_Node]."""
    n, d = x.shape
    nodes: list[_Node] = []

    def build(idx, depth):
        node_i = len(nodes)
        nodes.append(_Node(value=float(g[idx].mean()) if len(idx) else 0.0))
        if depth >= max_depth or len(idx) < 2 * min_leaf:
            return node_i
        if colsample < 1.0:
            feats = rng.choice(d, size=max(1, int(d * colsample)), replace=False)
        else:
            feats = range(d)
        gi = g[idx]
        parent_sse = float(((gi - gi.mean()) ** 2).sum())
        best = None  # (gain, feat, thr, left_idx, right_idx)
        for f in feats:
            col = x[idx, f]
            uniq = np.unique(col)
            if len(uniq) < 2:
                continue
            if len(uniq) <= _MAX_BINS:
                cand = uniq[:-1]
            else:
                cand = np.quantile(col, np.linspace(0.02, 0.98, _MAX_BINS))
            for thr in cand:
                lmask = col <= thr
                nl = int(lmask.sum())
                if nl < min_leaf or len(idx) - nl < min_leaf:
                    continue
                gl, gr = gi[lmask], gi[~lmask]
                sse = float(((gl - gl.mean()) ** 2).sum() + ((gr - gr.mean()) ** 2).sum())
                gain = parent_sse - sse
                if best is None or gain > best[0]:
                    best = (gain, int(f), float(thr), idx[lmask], idx[~lmask])
        if best is None or best[0] <= 1e-9:
            return node_i
        _, f, thr, li, ri = best
        nodes[node_i].feat = f
        nodes[node_i].thr = thr
        nodes[node_i].left = build(li, depth + 1)
        nodes[node_i].right = build(ri, depth + 1)
        return node_i

    build(np.arange(n), 0)
    return nodes


def _predict_tree(nodes, x):
    out = np.empty(len(x))
    for i in range(len(x)):
        row = x[i]
        j = 0
        while nodes[j].feat >= 0:
            j = nodes[j].left if row[nodes[j].feat] <= nodes[j].thr else nodes[j].right
        out[i] = nodes[j].value
    return out


class GBRT:
    """Gradient-boosted regression trees. ``loss`` is ``"l2"`` (mean) or
    ``"quantile"`` (pinball at ``alpha``)."""

    def __init__(self, base, trees, lr, loss, alpha):
        self.base = float(base)
        self.trees = trees  # list[list[_Node]]
        self.lr = float(lr)
        self.loss = loss
        self.alpha = float(alpha)

    @classmethod
    def fit(cls, x, y, *, n_estimators=200, learning_rate=0.05, max_depth=3,
            min_leaf=20, subsample=0.8, colsample=1.0, loss="l2", alpha=0.5,
            seed=0):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        rng = np.random.default_rng(seed)
        base = float(np.quantile(y, alpha) if loss == "quantile" else y.mean())
        f = np.full(len(y), base)
        trees: list[list[_Node]] = []
        for _ in range(n_estimators):
            if loss == "quantile":
                grad = np.where(y >= f, alpha, alpha - 1.0)
            else:
                grad = y - f
            if subsample < 1.0:
                sub = rng.choice(len(y), size=max(1, int(len(y) * subsample)),
                                 replace=False)
            else:
                sub = np.arange(len(y))
            tree = _fit_tree(x[sub], grad[sub], max_depth, min_leaf, rng, colsample)
            f = f + learning_rate * _predict_tree(tree, x)
            trees.append(tree)
        return cls(base, trees, learning_rate, loss, alpha)

    def predict(self, x):
        x = np.asarray(x, float)
        out = np.full(len(x), self.base)
        for tree in self.trees:
            out = out + self.lr * _predict_tree(tree, x)
        return out

    def to_json(self) -> str:
        return json.dumps({
            "base": self.base, "lr": self.lr, "loss": self.loss, "alpha": self.alpha,
            "trees": [
                [[n.feat, n.thr, n.left, n.right, n.value] for n in tree]
                for tree in self.trees
            ],
        })

    @classmethod
    def from_json(cls, s: str) -> GBRT:
        d = json.loads(s)
        trees = [
            [_Node(int(a), float(b), int(c), int(e), float(v)) for a, b, c, e, v in tree]
            for tree in d["trees"]
        ]
        return cls(d["base"], trees, d["lr"], d["loss"], d["alpha"])
