"""ForgeAtlas — Semantic search layer (Phase 3, P1-1 / P1-2).

Provides:
- SemanticSearch   — embedding model loader + in-memory vector store +
                     similarity ranking for ActionContract descriptions.

Integration contract
--------------------
Semantic search runs BEFORE capability filtering in the query path:

    1. rank_by_similarity(task_context, candidates, threshold)
       → ranked list of ActionContract, threshold-filtered
    2. capability filter (is_action_permitted) — runs on ranked list
    3. structured filters (resource_type, action_family) — applied last

This ordering guarantees the security invariant: no action appears in
results unless it passes both the similarity threshold AND the agent's
capability/trust check.

Graceful degradation
--------------------
If the embedding model fails to load for any reason (missing dependency,
corrupt model files, OOM), SemanticSearch silently disables itself.
rank_by_similarity() returns candidates in their original order when
semantic search is disabled.  Callers check `.enabled` before deciding
whether to use the semantic path.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import numpy as np

if TYPE_CHECKING:
    from dawn.concord.contracts_kernel import ContractRegistry
    from dawn.concord.types.contracts import ActionContract

_LOG = logging.getLogger(__name__)


class SemanticSearch:
    """Embedding-based similarity ranker for ActionContract descriptions.

    Lifecycle::

        ss = SemanticSearch("all-MiniLM-L6-v2")
        ss.load_model()            # tries to load; sets .enabled
        ss.embed_catalog(registry) # pre-computes all embeddings
        ranked = ss.rank_by_similarity(task_context, candidates, threshold=0.3)

    If load_model() fails, embed_catalog() is a no-op and rank_by_similarity()
    returns candidates unchanged.

    Attributes:
        enabled:     True when the model loaded successfully.
        model_name:  Name of the sentence-transformers model in use.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name: str = model_name
        self.enabled: bool = False
        self._model = None
        # key: "<resource_type>/<action_name>", value: unit-normalised embedding
        self._embeddings: dict[str, np.ndarray] = {}

    # ── Model lifecycle ───────────────────────────────────────────────────────

    def load_model(self) -> bool:
        """Attempt to load the embedding model.

        Returns:
            True if the model loaded successfully; False otherwise (model
            failed to import or initialise — service continues without it).
        """
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.model_name)
            self.enabled = True
            _LOG.info("SemanticSearch: model '%s' loaded.", self.model_name)
            return True
        except Exception as exc:  # ImportError, OSError, RuntimeError, etc.
            self._model = None
            self.enabled = False
            _LOG.warning(
                "SemanticSearch: model '%s' failed to load (%s). "
                "Structured filtering only.",
                self.model_name,
                exc,
            )
            return False

    # ── Catalog embedding ─────────────────────────────────────────────────────

    def embed_catalog(self, registry: "ContractRegistry") -> None:
        """Pre-compute and cache unit-normalised embeddings for every action.

        Called once at service startup after the catalog is loaded.  If the
        model is not enabled this is a no-op.

        Args:
            registry: The loaded ContractRegistry to embed.
        """
        if not self.enabled or self._model is None:
            return

        self._embeddings = {}
        for rt in sorted(registry.registered_resource_types()):
            for name in sorted(registry.registered_actions(rt)):
                try:
                    ac = registry.lookup_action(rt, name)
                    emb = self._model.encode(ac.description, convert_to_numpy=True)
                    self._embeddings[f"{rt}/{name}"] = _normalise(emb)
                except Exception as exc:
                    _LOG.warning(
                        "SemanticSearch: failed to embed '%s/%s': %s", rt, name, exc
                    )

        _LOG.info(
            "SemanticSearch: embedded %d actions.", len(self._embeddings)
        )

    # ── Similarity ranking (P1-2) ─────────────────────────────────────────────

    def rank_by_similarity(
        self,
        task_context: str,
        candidates: list["ActionContract"],
        threshold: float = 0.3,
    ) -> list["ActionContract"]:
        """Rank *candidates* by cosine similarity to *task_context*.

        Args:
            task_context: Natural-language description of what the agent needs.
            candidates:   List of ActionContracts to rank (typically the full
                          catalog for the queried resource types).
            threshold:    Minimum cosine similarity (0.0–1.0).  Candidates
                          below this score are excluded.  Default 0.3.

        Returns:
            Candidates sorted by descending similarity, filtered to those
            meeting the threshold.  If semantic search is disabled, returns
            *candidates* in their original order (no filtering by threshold).
        """
        if not self.enabled or self._model is None:
            return list(candidates)

        if not candidates:
            return []

        if not task_context or not task_context.strip():
            return list(candidates)

        try:
            query_emb = _normalise(
                self._model.encode(task_context, convert_to_numpy=True)
            )
        except Exception as exc:
            _LOG.warning("SemanticSearch: failed to encode task_context: %s", exc)
            return list(candidates)

        scored: list[tuple[ActionContract, float]] = []
        for ac in candidates:
            key = f"{ac.resource_type}/{ac.action_name}"
            stored_emb = self._embeddings.get(key)
            if stored_emb is None:
                # Action was added after embed_catalog() — compute on demand.
                try:
                    stored_emb = _normalise(
                        self._model.encode(ac.description, convert_to_numpy=True)
                    )
                    self._embeddings[key] = stored_emb
                except Exception:
                    continue  # skip unembeddable action

            similarity = float(np.dot(query_emb, stored_emb))
            if similarity >= threshold:
                scored.append((ac, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [ac for ac, _ in scored]

    def similarity_score(self, task_context: str, action: "ActionContract") -> Optional[float]:
        """Return the cosine similarity between task_context and action description.

        Returns None if semantic search is disabled or encoding fails.
        Useful for testing and debugging.
        """
        if not self.enabled or self._model is None:
            return None
        try:
            q = _normalise(self._model.encode(task_context, convert_to_numpy=True))
            key = f"{action.resource_type}/{action.action_name}"
            a = self._embeddings.get(key)
            if a is None:
                a = _normalise(self._model.encode(action.description, convert_to_numpy=True))
            return float(np.dot(q, a))
        except Exception:
            return None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _normalise(v: np.ndarray) -> np.ndarray:
    """Return unit-length vector; return v unchanged if norm is zero."""
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else v
